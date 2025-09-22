#!/bin/bash
# CloudVault Release Script
# Usage: ./scripts/release.sh 1.0.1 "Bug fixes and improvements"

set -e

if [ $# -lt 1 ]; then
    echo "Usage: $0 <version> [release_message]"
    echo "Example: $0 1.0.1 'Bug fixes and improvements'"
    exit 1
fi

VERSION=$1
MESSAGE=${2:-"Release v$VERSION"}

echo "🚀 Creating CloudVault release v$VERSION"
echo "📝 Message: $MESSAGE"

# Update version in files
echo "📄 Updating version in pyproject.toml..."
sed -i "s/version = \".*\"/version = \"$VERSION\"/" pyproject.toml

echo "📄 Updating version in __init__.py..."
sed -i "s/__version__ = \".*\"/__version__ = \"$VERSION\"/" cloudvault_discovery/__init__.py

# Test build
echo "🔨 Testing build..."
python -m build --quiet

# Test installation
echo "🧪 Testing installation..."
pip install -q dist/cloudvault4-$VERSION-py3-none-any.whl
cloudvault --help > /dev/null
echo "✅ Build test successful!"

# Clean up test files
rm -rf dist/ build/ *.egg-info/

# Git operations
echo "📝 Committing changes..."
git add pyproject.toml cloudvault_discovery/__init__.py
git commit -m "Bump version to v$VERSION"

echo "🏷️  Creating tag..."
git tag -a "v$VERSION" -m "$MESSAGE"

echo "📤 Pushing changes..."
git push origin main
git push origin "v$VERSION"

echo ""
echo "✅ Release v$VERSION created successfully!"
echo "🎯 GitHub Actions will automatically:"
echo "   • Build and test the package"
echo "   • Publish to PyPI"
echo "   • Create GitHub release"
echo ""
echo "📱 Check progress at: https://github.com/ibrahmsql/CloudVault/actions"
echo "📦 PyPI package: https://pypi.org/project/cloudvault4/"