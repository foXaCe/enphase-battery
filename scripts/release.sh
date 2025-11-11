#!/bin/bash
# Release helper script for Enphase Battery integration
# Usage: ./scripts/release.sh [version]
# Example: ./scripts/release.sh 2.27.4

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

if [ -z "$1" ]; then
    echo -e "${RED}Error: Version number required${NC}"
    echo "Usage: $0 <version>"
    echo "Example: $0 2.27.4"
    exit 1
fi

NEW_VERSION="$1"
TAG="v${NEW_VERSION}"

echo -e "${YELLOW}=== Enphase Battery Release Script ===${NC}"
echo ""
echo "New version: ${NEW_VERSION}"
echo "Git tag: ${TAG}"
echo ""

# Check if working directory is clean
if [[ -n $(git status -s) ]]; then
    echo -e "${RED}Error: Working directory is not clean${NC}"
    echo "Please commit or stash your changes first"
    git status -s
    exit 1
fi

# Check if tag already exists
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo -e "${RED}Error: Tag $TAG already exists${NC}"
    exit 1
fi

# Update manifest.json version
echo -e "${GREEN}Updating manifest.json...${NC}"
MANIFEST_FILE="custom_components/enphase_battery/manifest.json"

if [ ! -f "$MANIFEST_FILE" ]; then
    echo -e "${RED}Error: manifest.json not found${NC}"
    exit 1
fi

# Use jq to update version if available, otherwise use sed
if command -v jq >/dev/null 2>&1; then
    TMP_FILE=$(mktemp)
    jq --arg version "$NEW_VERSION" '.version = $version' "$MANIFEST_FILE" > "$TMP_FILE"
    mv "$TMP_FILE" "$MANIFEST_FILE"
else
    sed -i "s/\"version\": \".*\"/\"version\": \"$NEW_VERSION\"/" "$MANIFEST_FILE"
fi

echo "  ✓ Updated manifest.json to version ${NEW_VERSION}"

# Update pyproject.toml version
echo -e "${GREEN}Updating pyproject.toml...${NC}"
PYPROJECT_FILE="pyproject.toml"

if [ -f "$PYPROJECT_FILE" ]; then
    sed -i "s/^version = \".*\"/version = \"$NEW_VERSION\"/" "$PYPROJECT_FILE"
    echo "  ✓ Updated pyproject.toml to version ${NEW_VERSION}"
fi

# Show changes
echo ""
echo -e "${YELLOW}Changes to be committed:${NC}"
git diff custom_components/enphase_battery/manifest.json pyproject.toml

# Confirm
echo ""
read -p "Do you want to commit and create tag $TAG? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Aborted${NC}"
    git checkout -- custom_components/enphase_battery/manifest.json pyproject.toml
    exit 1
fi

# Commit
echo -e "${GREEN}Creating commit...${NC}"
git add custom_components/enphase_battery/manifest.json pyproject.toml
git commit -m "chore: bump version to ${NEW_VERSION}"

# Create tag
echo -e "${GREEN}Creating tag ${TAG}...${NC}"
git tag -a "$TAG" -m "Release ${TAG}"

# Push
echo ""
read -p "Do you want to push to remote? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}Pushing to remote...${NC}"
    git push origin main
    git push origin "$TAG"

    echo ""
    echo -e "${GREEN}✓ Release ${TAG} created successfully!${NC}"
    echo ""
    echo "GitHub Actions will now:"
    echo "  1. Run quality checks"
    echo "  2. Create the release"
    echo "  3. Generate ZIP archive"
    echo ""
    echo "Check progress at:"
    echo "  https://github.com/foXaCe/enphase-battery/actions"
    echo ""
    echo "Release will be available at:"
    echo "  https://github.com/foXaCe/enphase-battery/releases/tag/${TAG}"
else
    echo ""
    echo -e "${YELLOW}Changes committed locally but not pushed${NC}"
    echo "To push later, run:"
    echo "  git push origin main"
    echo "  git push origin $TAG"
fi
