#!/usr/bin/env python3
"""
Vider deployment script — builds, pushes, and deploys to Kubernetes.

Usage:
    python deploy.py                    # Build and deploy
    python deploy.py --dry-run          # Preview actions without executing
    python deploy.py --help             # Show help
"""

import argparse
import logging
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class CommandRunner:
    """Execute shell commands with error handling and dry-run support."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def run(
        self,
        cmd: str | list[str],
        check: bool = True,
        capture: bool = False,
        description: Optional[str] = None,
    ) -> tuple[int, str]:
        """Run a shell command.
        
        Args:
            cmd: Command string or list of arguments
            check: Raise exception if command fails
            capture: Capture and return stdout
            description: Human-readable description for logging
            
        Returns:
            (exit_code, stdout)
        """
        if isinstance(cmd, list):
            cmd_str = " ".join(shlex.quote(str(c)) for c in cmd)
        else:
            cmd_str = cmd

        description_str = f" ({description})" if description else ""
        logger.info(f"$ {cmd_str}{description_str}")

        if self.dry_run:
            return 0, ""

        try:
            result = subprocess.run(
                cmd_str if isinstance(cmd, str) else cmd,
                shell=isinstance(cmd, str),
                check=check,
                capture_output=capture,
                text=True,
            )
            if capture:
                return result.returncode, result.stdout.strip()
            return result.returncode, ""
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed with exit code {e.returncode}")
            if e.stdout:
                logger.error(f"stdout: {e.stdout}")
            if e.stderr:
                logger.error(f"stderr: {e.stderr}")
            if check:
                raise
            return e.returncode, e.stdout or ""


class GitManager:
    """Manage git operations (state, tagging)."""

    def __init__(self, runner: CommandRunner):
        self.runner = runner

    def get_current_branch(self) -> str:
        """Get current git branch."""
        _, output = self.runner.run(
            "git rev-parse --abbrev-ref HEAD",
            capture=True,
            description="Get current branch",
        )
        return output

    def get_commit_sha(self, short: bool = True) -> str:
        """Get current commit SHA."""
        cmd = ["git", "rev-parse"]
        if short:
            cmd.append("--short")
        cmd.append("HEAD")
        _, output = self.runner.run(
            cmd,
            capture=True,
            description="Get commit SHA",
        )
        return output

    def is_dirty(self) -> bool:
        """Check if working tree has uncommitted changes."""
        _, output = self.runner.run(
            "git status --porcelain",
            capture=True,
            description="Check git status",
        )
        return bool(output.strip())

    def stage_all(self) -> None:
        """Stage all changes."""
        if not self.is_dirty():
            logger.info("No changes to stage")
            return
        self.runner.run("git add -A", description="Stage all changes")

    def amend_commit(self) -> None:
        """Amend the last commit."""
        self.runner.run(
            "git commit --amend --no-edit",
            check=False,
            description="Amend last commit",
        )

    def create_tag(self, tag: str) -> None:
        """Create and push a git tag."""
        self.runner.run(f'git tag "{tag}"', description=f"Create tag: {tag}")
        self.runner.run("git push --tags", description="Push tags")


class ImageBuilder:
    """Build and push container images."""

    def __init__(self, runner: CommandRunner, registry: str, image_name: str, tls_verify: bool = True):
        self.runner = runner
        self.registry = registry
        self.image_name = image_name
        self._tls_flag = [] if tls_verify else ["--tls-verify=false"]

    def _ensure_podman_machine(self) -> None:
        """Start or init the podman machine when the daemon is unreachable."""
        logger.info("Attempting 'podman machine start'...")
        code, _ = self.runner.run(
            ["podman", "machine", "start"],
            check=False,
            description="Start podman machine",
        )
        if code == 0:
            return
        logger.warning("'podman machine start' failed; attempting 'podman machine init'...")
        self.runner.run(
            ["podman", "machine", "init"],
            description="Init podman machine",
        )
        self.runner.run(
            ["podman", "machine", "start"],
            description="Start podman machine after init",
        )

    def _podman_build(self, cmd: list[str]) -> tuple[int, str]:
        """Run podman build, streaming stdout while capturing stderr for error detection."""
        if self.runner.dry_run:
            cmd_str = " ".join(shlex.quote(str(c)) for c in cmd)
            logger.info(f"$ {cmd_str} (dry-run)")
            return 0, ""
        cmd_str = " ".join(shlex.quote(str(c)) for c in cmd)
        logger.info(f"$ {cmd_str}")
        result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        if result.stderr:
            sys.stderr.write(result.stderr)
        return result.returncode, result.stderr

    def build(self, tag: str) -> str:
        """Build image with podman.

        Returns:
            Full image reference (registry/name:tag)
        """
        full_image = f"{self.registry}/{self.image_name}:{tag}"
        cmd = [
            "podman", "build",
            *self._tls_flag,
            "-t", full_image,
            ".",
        ]
        max_attempts = 3
        exit_code = 1
        for attempt in range(1, max_attempts + 1):
            exit_code, stderr = self._podman_build(cmd)
            if exit_code == 0:
                return full_image
            if exit_code == 125:
                self._ensure_podman_machine()
                continue
            if "Segmentation fault" in stderr or "qemu" in stderr.lower():
                if attempt < max_attempts:
                    logger.warning(f"QEMU segfault on attempt {attempt}/{max_attempts}, retrying...")
                    continue
                raise RuntimeError(f"QEMU segfault persisted after {max_attempts} attempts")
            raise subprocess.CalledProcessError(exit_code, cmd)
        raise subprocess.CalledProcessError(exit_code, cmd)

    def push(self, image: str) -> None:
        """Push image to registry."""
        self.runner.run(["podman", "push", *self._tls_flag, image], description=f"Push image: {image}")

    def cleanup_local(self, keep_count: int = 5) -> None:
        """Remove old local images (keep last N)."""
        logger.info(f"Cleaning up local images (keeping last {keep_count})")
        self.runner.run(
            f'podman images "{self.registry}/{self.image_name}" --format "{{{{.ID}}}}" | tail -n +{keep_count + 1} | xargs -r podman rmi',
            check=False,
            description="Remove old images",
        )


class KubernetesDeployer:
    """Manage Kubernetes deployments."""

    def __init__(self, runner: CommandRunner, deployment: str, namespace: str = "default"):
        self.runner = runner
        self.deployment = deployment
        self.namespace = namespace

    def set_image(self, image: str, container: Optional[str] = None) -> None:
        """Update deployment image."""
        container_name = container or self.deployment
        cmd = [
            "kubectl", "set", "image",
            f"deployment/{self.deployment}",
            f"{container_name}={image}",
            f"--namespace={self.namespace}",
        ]
        self.runner.run(cmd, description=f"Update deployment image: {image}")

    def verify_rollout(self, timeout: int = 300) -> bool:
        """Wait for rollout to complete."""
        cmd = [
            "kubectl", "rollout", "status",
            f"deployment/{self.deployment}",
            f"--namespace={self.namespace}",
            f"--timeout={timeout}s",
        ]
        exit_code, _ = self.runner.run(cmd, check=False, description="Wait for rollout")
        return exit_code == 0


class Deployer:
    """Main deployment orchestrator."""

    def __init__(self, config: dict, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.runner = CommandRunner(dry_run=dry_run)
        self.git = GitManager(self.runner)
        
        # Initialize builders/deployers from config
        registry_config = config.get("registry", {})
        registry = registry_config.get("url", "ghcr.io/caf3babe")
        image_name = config.get("image_name", "vider")
        tls_verify = registry_config.get("tls_verify", True)
        self.builder = ImageBuilder(self.runner, registry, image_name, tls_verify=tls_verify)
        
        k8s_config = config.get("k8s", {})
        self.deployer = KubernetesDeployer(
            self.runner,
            k8s_config.get("deployment", "vider"),
            k8s_config.get("namespace", "default"),
        )

    def _get_version_tag(self) -> str:
        """Generate version tag (timestamp-sha)."""
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        sha = self.git.get_commit_sha(short=True)
        return f"{now}-{sha}"

    def _handle_git_state(self) -> None:
        """Handle dirty git working tree."""
        if not self.git.is_dirty():
            return
        
        logger.warning("Git working tree is dirty")
        if self.dry_run:
            logger.info("[DRY-RUN] Would stage and amend")
            return
        
        self.git.stage_all()
        self.git.amend_commit()
        logger.info("Staged changes and amended commit")

    def deploy(self) -> None:
        """Execute full deployment pipeline."""
        try:
            logger.info("=" * 60)
            logger.info("Vider Deployment")
            logger.info("=" * 60)
            
            # Check git state
            branch = self.git.get_current_branch()
            sha = self.git.get_commit_sha()
            logger.info(f"Branch: {branch} | Commit: {sha}")
            
            self._handle_git_state()
            
            # Build
            version_tag = self._get_version_tag()
            logger.info(f"\nBuilding image with tag: {version_tag}")
            image = self.builder.build(version_tag)
            
            # Push
            logger.info(f"\nPushing image: {image}")
            self.builder.push(image)
            
            # Also tag as 'latest'
            latest_image = image.rsplit(":", 1)[0] + ":latest"
            logger.info(f"\nTagging as latest: {latest_image}")
            self.runner.run(
                ["podman", "tag", image, latest_image],
                description="Tag as latest",
            )
            self.builder.push(latest_image)
            
            # Deploy to K8s
            logger.info(f"\nDeploying to Kubernetes")
            self.deployer.set_image(image)
            
            # Verify rollout
            logger.info("\nWaiting for rollout to complete...")
            if self.deployer.verify_rollout():
                logger.info("✓ Rollout successful")
            else:
                logger.warning("⚠ Rollout verification timed out")
            
            # Cleanup local images
            self.builder.cleanup_local()
            
            # Create git tag if configured
            if self.config.get("git", {}).get("auto_tag", True) and not self.dry_run:
                tag = f"v{version_tag}"
                logger.info(f"\nCreating git tag: {tag}")
                self.git.create_tag(tag)
            
            logger.info("\n" + "=" * 60)
            logger.info("✓ Deployment complete")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"\n✗ Deployment failed: {e}")
            sys.exit(1)


def load_config(config_file: Path) -> dict:
    """Load deployment configuration from YAML."""
    if not config_file.exists():
        logger.warning(f"Config file not found: {config_file}")
        # Return sensible defaults
        return {
            "registry": {"url": "ghcr.io/caf3babe"},
            "image_name": "vider",
            "k8s": {"deployment": "vider", "namespace": "default"},
            "git": {"auto_tag": True},
        }
    
    # Simple YAML parsing for our limited needs
    import json
    try:
        # Try to load as JSON first (for compatibility)
        with open(config_file) as f:
            return json.load(f)
    except:
        pass
    
    # Basic YAML parsing
    config = {}
    with open(config_file) as f:
        content = f.read()
    
    lines = content.split("\n")
    current_section = None
    current_section_dict = None
    
    for line in lines:
        # Strip and ignore empty lines and comments
        original_line = line
        line = line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        
        # Remove inline comments
        if "#" in line:
            line = line[:line.index("#")].rstrip()
        
        # Detect indentation
        indent = len(original_line) - len(original_line.lstrip())
        line = line.lstrip()
        
        if not ":" in line:
            continue
        
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        
        if indent == 0:
            # Top-level key
            current_section_dict = {}
            config[key] = current_section_dict
            current_section = key
        else:
            # Nested key
            if current_section_dict is None:
                continue
            
            # Parse value
            if value.lower() in ("true", "yes"):
                current_section_dict[key] = True
            elif value.lower() in ("false", "no"):
                current_section_dict[key] = False
            elif value.isdigit():
                current_section_dict[key] = int(value)
            else:
                current_section_dict[key] = value
    
    # Handle top-level simple keys (not sections)
    for key, value in config.items():
        if isinstance(value, dict) and len(value) == 0:
            # This was likely a value, not a section
            # Re-parse to find the actual value
            for line in lines:
                line = line.rstrip()
                if line.lstrip().startswith("#") or not line:
                    continue
                if "#" in line:
                    line = line[:line.index("#")].rstrip()
                if ":" in line:
                    k, v = line.split(":", 1)
                    if k.strip() == key:
                        config[key] = v.strip()
                        break
    
    return config


def main():
    parser = argparse.ArgumentParser(
        description="Deploy vider to Kubernetes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without executing",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("deploy.config.yaml"),
        help="Path to deployment config file",
    )
    
    args = parser.parse_args()
    
    config = load_config(args.config)
    deployer = Deployer(config, dry_run=args.dry_run)
    
    if args.dry_run:
        logger.info("=" * 60)
        logger.info("DRY-RUN MODE — No changes will be made")
        logger.info("=" * 60)
    
    deployer.deploy()


if __name__ == "__main__":
    main()
