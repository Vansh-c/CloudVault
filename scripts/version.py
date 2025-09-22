#!/usr/bin/env python3
"""
CloudVault Version Management Script
Supports semantic versioning and automatic version bumping
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

def get_current_version():
    """Extract current version from pyproject.toml"""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        raise FileNotFoundError("pyproject.toml not found")
    
    content = pyproject_path.read_text()
    match = re.search(r'version = "([^"]+)"', content)
    if not match:
        raise ValueError("Version not found in pyproject.toml")
    
    return match.group(1)

def parse_version(version_str):
    """Parse semantic version string"""
    match = re.match(r'(\d+)\.(\d+)\.(\d+)(?:-([^+]+))?(?:\+(.+))?', version_str)
    if not match:
        raise ValueError(f"Invalid semantic version: {version_str}")
    
    major, minor, patch = map(int, match.groups()[:3])
    prerelease = match.group(4)
    build = match.group(5)
    
    return {
        'major': major,
        'minor': minor,
        'patch': patch,
        'prerelease': prerelease,
        'build': build,
        'full': version_str
    }

def bump_version(current_version, bump_type):
    """Bump version based on semantic versioning"""
    version = parse_version(current_version)
    
    if bump_type == 'major':
        version['major'] += 1
        version['minor'] = 0
        version['patch'] = 0
    elif bump_type == 'minor':
        version['minor'] += 1
        version['patch'] = 0
    elif bump_type == 'patch':
        version['patch'] += 1
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")
    
    # Clear prerelease and build for main releases
    version['prerelease'] = None
    version['build'] = None
    
    new_version = f"{version['major']}.{version['minor']}.{version['patch']}"
    return new_version

def update_version_files(new_version):
    """Update version in all relevant files"""
    files_updated = []
    
    # Update pyproject.toml
    pyproject_path = Path("pyproject.toml")
    content = pyproject_path.read_text()
    updated_content = re.sub(r'version = "[^"]+"', f'version = "{new_version}"', content)
    pyproject_path.write_text(updated_content)
    files_updated.append("pyproject.toml")
    
    # Update __init__.py
    init_path = Path("cloudvault_discovery/__init__.py")
    if init_path.exists():
        content = init_path.read_text()
        updated_content = re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new_version}"', content)
        init_path.write_text(updated_content)
        files_updated.append("cloudvault_discovery/__init__.py")
    
    return files_updated

def get_git_changes():
    """Get list of changes since last tag"""
    try:
        # Get latest tag
        result = subprocess.run(['git', 'describe', '--tags', '--abbrev=0'], 
                              capture_output=True, text=True, check=True)
        last_tag = result.stdout.strip()
        
        # Get commits since last tag
        result = subprocess.run(['git', 'log', '--oneline', f'{last_tag}..HEAD'], 
                              capture_output=True, text=True, check=True)
        changes = result.stdout.strip().split('\n') if result.stdout.strip() else []
        
        return last_tag, changes
    except subprocess.CalledProcessError:
        return None, []

def create_changelog(new_version, changes):
    """Create changelog entry"""
    changelog = f"## v{new_version}\n\n"
    
    if changes:
        changelog += "### Changes:\n"
        for change in changes:
            if change.strip():
                changelog += f"- {change}\n"
    else:
        changelog += "- Initial release\n"
    
    changelog += f"\n### Installation:\n```bash\npip install cloudvault4=={new_version}\n```\n\n"
    
    return changelog

def main():
    parser = argparse.ArgumentParser(description='CloudVault Version Management')
    parser.add_argument('action', choices=['show', 'bump', 'set'], 
                       help='Action to perform')
    parser.add_argument('--type', choices=['major', 'minor', 'patch'], 
                       help='Type of version bump (for bump action)')
    parser.add_argument('--version', help='Specific version to set (for set action)')
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show what would be done without making changes')
    
    args = parser.parse_args()
    
    try:
        current_version = get_current_version()
        print(f"📋 Current version: {current_version}")
        
        if args.action == 'show':
            version_info = parse_version(current_version)
            print(f"📊 Version breakdown:")
            print(f"   Major: {version_info['major']}")
            print(f"   Minor: {version_info['minor']}")
            print(f"   Patch: {version_info['patch']}")
            if version_info['prerelease']:
                print(f"   Pre-release: {version_info['prerelease']}")
            if version_info['build']:
                print(f"   Build: {version_info['build']}")
                
            last_tag, changes = get_git_changes()
            if last_tag:
                print(f"\n📝 Changes since {last_tag}:")
                if changes:
                    for change in changes:
                        if change.strip():
                            print(f"   • {change}")
                else:
                    print("   No changes detected")
        
        elif args.action == 'bump':
            if not args.type:
                print("❌ --type is required for bump action")
                sys.exit(1)
                
            new_version = bump_version(current_version, args.type)
            print(f"🚀 New version: {new_version}")
            
            if not args.dry_run:
                files_updated = update_version_files(new_version)
                print(f"✅ Updated files: {', '.join(files_updated)}")
                
                # Generate changelog
                last_tag, changes = get_git_changes()
                changelog = create_changelog(new_version, changes)
                changelog_path = Path("CHANGELOG.md")
                
                if changelog_path.exists():
                    existing_content = changelog_path.read_text()
                    changelog_path.write_text(changelog + existing_content)
                else:
                    changelog_path.write_text(changelog)
                print("📝 Updated CHANGELOG.md")
            else:
                print("🔍 Dry run - no files were modified")
        
        elif args.action == 'set':
            if not args.version:
                print("❌ --version is required for set action")
                sys.exit(1)
                
            # Validate version format
            parse_version(args.version)
            print(f"🎯 Setting version to: {args.version}")
            
            if not args.dry_run:
                files_updated = update_version_files(args.version)
                print(f"✅ Updated files: {', '.join(files_updated)}")
            else:
                print("🔍 Dry run - no files were modified")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()