#!/usr/bin/env python3
"""
Sync video recordings from server to local machine.

Usage:
    # Download all videos
    python scripts/sync_videos.py user@server:/path/to/tg-automation/logs/videos/ ./local_videos/

    # Download and delete from server
    python scripts/sync_videos.py user@server:/path/to/logs/videos/ ./local_videos/ --delete-after

    # Specify SSH key
    python scripts/sync_videos.py user@server:/path/ ./local/ -i ~/.ssh/mykey

    # Dry run (show what would be done)
    python scripts/sync_videos.py user@server:/path/ ./local/ --dry-run

Examples:
    # Sync from default server path
    python scripts/sync_videos.py admin@81.30.105.134:/home/admin/tg-automatizamtion/logs/videos/ ./videos/

    # Sync and remove from server after download
    python scripts/sync_videos.py admin@81.30.105.134:/home/admin/tg-automatizamtion/logs/videos/ ./videos/ -d
"""

import argparse
import subprocess
import sys
from pathlib import Path


def sync_videos(
    remote_path: str,
    local_path: str,
    delete_after: bool = False,
    ssh_key: str = None,
    dry_run: bool = False
) -> bool:
    """
    Sync videos from remote server using rsync.

    Args:
        remote_path: Remote path (user@host:/path/to/videos/)
        local_path: Local destination directory
        delete_after: Delete files from server after successful download
        ssh_key: Path to SSH private key
        dry_run: Show what would be done without actually doing it

    Returns:
        True if successful, False otherwise
    """
    # Create local directory if doesn't exist
    local_dir = Path(local_path)
    local_dir.mkdir(parents=True, exist_ok=True)

    # Build rsync command
    cmd = ["rsync", "-avz", "--progress"]

    if dry_run:
        cmd.append("--dry-run")
        print("[DRY RUN] Showing what would be transferred...")

    if delete_after:
        cmd.append("--remove-source-files")
        print("[WARNING] Files will be DELETED from server after download!")

    if ssh_key:
        cmd.extend(["-e", f"ssh -i {ssh_key}"])

    # Add source and destination
    cmd.append(remote_path)
    cmd.append(str(local_dir) + "/")

    print(f"\nRunning: {' '.join(cmd)}\n")
    print("-" * 60)

    try:
        result = subprocess.run(cmd, check=True)
        print("-" * 60)

        if result.returncode == 0:
            print("\n[SUCCESS] Sync completed!")
            if delete_after and not dry_run:
                print("[INFO] Files have been removed from server")
            return True
        return False

    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] rsync failed with code {e.returncode}", file=sys.stderr)
        return False

    except FileNotFoundError:
        print("\n[ERROR] rsync not found. Please install it:", file=sys.stderr)
        print("  macOS: brew install rsync", file=sys.stderr)
        print("  Ubuntu/Debian: sudo apt install rsync", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Sync video recordings from server to local machine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s admin@server:/path/logs/videos/ ./my_videos/
  %(prog)s admin@server:/path/logs/videos/ ./my_videos/ --delete-after
  %(prog)s admin@server:/path/logs/videos/ ./my_videos/ -i ~/.ssh/id_rsa
  %(prog)s admin@server:/path/logs/videos/ ./my_videos/ --dry-run
        """
    )
    parser.add_argument(
        "remote_path",
        help="Remote path in format: user@host:/path/to/videos/"
    )
    parser.add_argument(
        "local_path",
        help="Local destination directory"
    )
    parser.add_argument(
        "--delete-after", "-d",
        action="store_true",
        help="Delete files from server after successful download"
    )
    parser.add_argument(
        "-i", "--ssh-key",
        help="Path to SSH private key"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without actually doing it"
    )

    args = parser.parse_args()

    # Validate remote path format
    if "@" not in args.remote_path or ":" not in args.remote_path:
        print("[ERROR] Remote path must be in format: user@host:/path/", file=sys.stderr)
        print(f"Got: {args.remote_path}", file=sys.stderr)
        sys.exit(1)

    success = sync_videos(
        remote_path=args.remote_path,
        local_path=args.local_path,
        delete_after=args.delete_after,
        ssh_key=args.ssh_key,
        dry_run=args.dry_run
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
