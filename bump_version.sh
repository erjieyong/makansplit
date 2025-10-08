#!/bin/bash
set -e

# Version Bump Script for MakanSplit
# Usage: ./bump_version.sh [major|minor|patch]

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

if [ ! -f "VERSION" ]; then
    echo -e "${RED}❌ VERSION file not found${NC}"
    exit 1
fi

CURRENT_VERSION=$(cat VERSION)
echo -e "${YELLOW}Current version: ${GREEN}$CURRENT_VERSION${NC}"

# Parse version
IFS='.' read -r -a VERSION_PARTS <<< "$CURRENT_VERSION"
MAJOR="${VERSION_PARTS[0]}"
MINOR="${VERSION_PARTS[1]}"
PATCH="${VERSION_PARTS[2]}"

# Determine bump type
BUMP_TYPE="${1:-patch}"

case "$BUMP_TYPE" in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
    *)
        echo -e "${RED}❌ Invalid bump type. Use: major, minor, or patch${NC}"
        exit 1
        ;;
esac

NEW_VERSION="$MAJOR.$MINOR.$PATCH"
echo -e "${YELLOW}New version: ${GREEN}$NEW_VERSION${NC}"

# Confirm
read -p "Bump version to $NEW_VERSION? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}Cancelled${NC}"
    exit 0
fi

# Update VERSION file
echo "$NEW_VERSION" > VERSION
echo -e "${GREEN}✓ Updated VERSION file${NC}"

# Update CHANGELOG
TODAY=$(date +%Y-%m-%d)
echo -e "\n${YELLOW}Updating CHANGELOG.md...${NC}"
echo -e "${YELLOW}Please edit CHANGELOG.md to add release notes for version $NEW_VERSION${NC}"

# Add entry to CHANGELOG if it doesn't exist
if ! grep -q "\[$NEW_VERSION\]" CHANGELOG.md; then
    # Insert new version after "## [Unreleased]"
    sed -i.bak "/## \[Unreleased\]/a\\
\\
## [$NEW_VERSION] - $TODAY\\
\\
### Added\\
- \\
\\
### Changed\\
- \\
\\
### Fixed\\
- \\
" CHANGELOG.md
    rm CHANGELOG.md.bak 2>/dev/null || true
    echo -e "${GREEN}✓ Added $NEW_VERSION section to CHANGELOG.md${NC}"
else
    echo -e "${YELLOW}⚠️  Version $NEW_VERSION already exists in CHANGELOG.md${NC}"
fi

# Git operations
if git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "\n${YELLOW}Git operations:${NC}"

    # Show changes
    echo -e "${YELLOW}Changes to commit:${NC}"
    git diff VERSION CHANGELOG.md

    read -p "Commit and tag this version? (y/N) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git add VERSION CHANGELOG.md
        git commit -m "chore: bump version to $NEW_VERSION

See CHANGELOG.md for details.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"

        git tag -a "v$NEW_VERSION" -m "Release version $NEW_VERSION

See CHANGELOG.md for details."

        echo -e "${GREEN}✓ Committed and tagged version $NEW_VERSION${NC}"
        echo -e "\n${YELLOW}💡 Push changes:${NC}"
        echo -e "git push origin main && git push origin v$NEW_VERSION"
    fi
else
    echo -e "${YELLOW}⚠️  Not a git repository${NC}"
fi

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}✅ Version bumped to $NEW_VERSION${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "\n${YELLOW}Next steps:${NC}"
echo -e "1. Edit CHANGELOG.md to add release notes"
echo -e "2. Push to git: ${GREEN}git push origin main && git push origin v$NEW_VERSION${NC}"
echo -e "3. Deploy: ${GREEN}./deploy.sh${NC}"
