#!/usr/bin/env python3
"""
Fix properties.json missing in Donut Browser Camoufox installations.

This script copies properties.json from Resources/ to MacOS/ directory
for all Camoufox versions installed by Donut Browser.

See: https://github.com/daijro/camoufox/issues/210
"""

import os
import shutil
from pathlib import Path


def find_donut_camoufox_installations() -> list[Path]:
    """Find all Camoufox installations in Donut Browser directory."""
    donut_base = Path.home() / "Library/Application Support/DonutBrowserDev/binaries/camoufox"
    
    if not donut_base.exists():
        print(f"Donut Browser directory not found: {donut_base}")
        return []
    
    installations = []
    for version_dir in donut_base.iterdir():
        if version_dir.is_dir():
            camoufox_app = version_dir / "Camoufox.app"
            if camoufox_app.exists():
                installations.append(camoufox_app)
    
    return installations


def fix_properties_json(camoufox_app: Path) -> bool:
    """
    Copy properties.json from Resources/ to MacOS/ if missing.
    
    Args:
        camoufox_app: Path to Camoufox.app directory
        
    Returns:
        True if fixed successfully, False otherwise
    """
    source = camoufox_app / "Contents/Resources/properties.json"
    target = camoufox_app / "Contents/MacOS/properties.json"
    
    # Check if source exists
    if not source.exists():
        print(f"  ✗ Source file not found: {source}")
        return False
    
    # Check if target already exists
    if target.exists():
        print(f"  ✓ Already exists: {target}")
        return True
    
    # Copy file
    try:
        shutil.copy2(source, target)
        print(f"  ✓ Copied: {source.name} → {target.parent.name}/")
        return True
    except Exception as e:
        print(f"  ✗ Failed to copy: {e}")
        return False


def main():
    """Main function."""
    print("Fixing properties.json for Donut Browser Camoufox installations...\n")
    
    installations = find_donut_camoufox_installations()
    
    if not installations:
        print("No Camoufox installations found in Donut Browser.")
        return
    
    print(f"Found {len(installations)} installation(s):\n")
    
    fixed_count = 0
    for camoufox_app in installations:
        version = camoufox_app.parent.name
        print(f"Processing {version}:")
        
        if fix_properties_json(camoufox_app):
            fixed_count += 1
        
        print()
    
    print(f"Summary: {fixed_count}/{len(installations)} installation(s) fixed successfully.")


if __name__ == "__main__":
    main()
