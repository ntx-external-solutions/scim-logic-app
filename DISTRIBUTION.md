# Distribution Guide

This guide explains how to package and share this solution with customers.

## Repository Structure

The repository is now organized for easy distribution:

```
scim-logic-app/
├── README.md                      # Main documentation (start here)
├── QUICKSTART.md                  # 15-minute setup guide
├── DEPLOY.md                      # Detailed deployment instructions
├── TESTING.md                     # Comprehensive testing procedures
├── VALIDATION.md                  # Post-deployment validation checklist
├── MAPPING_MODES.md              # Guide to mapping modes
├── ARCHITECTURE_COMPARISON.md     # Unified vs separate approaches
├── deploy.sh                      # Automated deployment script ⭐
├── .gitignore                     # Protects secrets from git
│
├── logic-app/
│   ├── azuredeploy.json          # Main ARM template (unified approach)
│   ├── azuredeploy-separate.json # Alternative: separate workflows
│   ├── azuredeploy.parameters.template.json  # Template for parameters
│   └── azuredeploy.parameters.local.json     # Gitignored (has secrets)
│
└── config/
    └── role-mapping.json          # Example role mapping configuration
```

## Distribution Checklist

Before sharing with a customer:

### 1. Clean Up Secrets

- [ ] Remove `logic-app/azuredeploy.parameters.local.json` (contains API key)
- [ ] Verify `.gitignore` is in place
- [ ] Run: `git status` to ensure no secrets are tracked

```bash
# Clean up any local deployment files
rm -f logic-app/azuredeploy.parameters.local.json

# Verify nothing sensitive is tracked
git status
```

### 2. Update Repository URL

- [ ] Update clone URL in README.md and QUICKSTART.md
- [ ] Add repository URL to all documentation

### 3. Add License (Optional)

- [ ] Choose a license (MIT, Apache 2.0, etc.)
- [ ] Add LICENSE file to repository
- [ ] Update README.md with license badge

### 4. Create Release Package

**Option A: GitHub Repository**

1. Create a GitHub repository
2. Push all files (secrets already gitignored)
3. Create a release with tag (v1.0.0)
4. Share repository URL with customers

**Option B: ZIP Package**

```bash
# Create distributable ZIP
cd /Users/jonathanbutler/Documents/Development/Nintex
zip -r scim-logic-app-v1.0.zip scim-logic-app/ \
  -x "*.git*" \
  -x "*/.DS_Store" \
  -x "*/logic-app/azuredeploy.parameters.local.json"
```

## Customer Handoff

### Provide to Customer

1. **Repository/ZIP** containing all files
2. **Quick Start Link**: Point them to `QUICKSTART.md`
3. **Prerequisites List**:
   - Azure subscription
   - Process Manager SCIM API key
   - Entra ID admin access

### Installation Instructions

Provide customers with:

```
🚀 Process Manager SCIM Sync - Getting Started

1. Download/Clone this repository
2. Open QUICKSTART.md
3. Run: ./deploy.sh
4. Follow the prompts
5. Authorize Office 365 connection in Azure Portal
6. Test with a user update

Estimated time: 15 minutes
```

### Support Documentation

Direct customers to:

1. **QUICKSTART.md** - For initial setup
2. **VALIDATION.md** - To verify deployment
3. **TESTING.md** - For comprehensive testing
4. **README.md** - For detailed reference
5. **MAPPING_MODES.md** - To choose mapping strategy

## Customization Guide for Customers

### Common Customizations

**1. Change Mapping Mode**

Edit `deploy.sh` default from:
```bash
MAPPING_MODE=${MAPPING_MODE:-dynamic}
```

To:
```bash
MAPPING_MODE=${MAPPING_MODE:-mapped}
```

**2. Pre-configure Resource Group**

Edit `deploy.sh`:
```bash
RESOURCE_GROUP=${RESOURCE_GROUP:-your-company-scim}
```

**3. Customize Role Mappings**

Edit `config/role-mapping.json` with customer-specific mappings before distribution.

## Version Control

### Semantic Versioning

Use semantic versioning for releases:

- **v1.0.0** - Initial unified Logic App release
- **v1.1.0** - Add new features (e.g., additional mapping options)
- **v1.0.1** - Bug fixes and documentation updates

### Changelog

Maintain a CHANGELOG.md file:

```markdown
# Changelog

## [1.0.0] - 2026-03-05

### Added
- Unified Logic App combining department and group sync
- Automated deployment script
- Comprehensive documentation suite
- Validation checklist

### Changed
- Made unified approach the default (replaced separate workflows)
- Improved deploy.sh with better prompts

### Removed
- Deprecated separate Logic App templates (moved to azuredeploy-separate.json)
```

## Deployment Options for Customers

### Option 1: Automated Script (Recommended)

```bash
./deploy.sh
```

**Best for:** Most customers, fast deployment

### Option 2: Manual Azure CLI

Follow `DEPLOY.md` for step-by-step Azure CLI commands.

**Best for:** Customers who need full control

### Option 3: Azure Portal

Use ARM template deployment in Azure Portal.

**Best for:** Customers uncomfortable with CLI

### Option 4: Infrastructure as Code

Integrate into Terraform/Bicep pipelines.

**Best for:** Enterprise customers with existing IaC

## Ongoing Maintenance

### Customer Responsibilities

- **Monitor** Logic App runs for failures
- **Update** role mappings as departments/groups change
- **Maintain** SCIM API key security
- **Review** user role assignments periodically

### Your Responsibilities (as maintainer)

- **Update** documentation for clarity
- **Fix** bugs in Logic App workflow
- **Add** requested features
- **Publish** new releases

## Support Model

### Documentation-Based Support

Customers should be able to:
- ✅ Deploy without assistance (using QUICKSTART.md)
- ✅ Troubleshoot common issues (using VALIDATION.md)
- ✅ Test thoroughly (using TESTING.md)
- ✅ Understand architecture (using README.md)

### Escalation Path

If customers need help:

1. **Check documentation** (README.md, QUICKSTART.md, etc.)
2. **Run validation** (VALIDATION.md checklist)
3. **Review Logic App run history** in Azure Portal
4. **Contact support** with specific error messages

## Pre-Distribution Testing

Before giving to a customer, verify:

- [ ] Fresh deployment works in a clean Azure subscription
- [ ] All documentation links work
- [ ] deploy.sh completes successfully
- [ ] VALIDATION.md tests all pass
- [ ] No secrets in repository
- [ ] README.md clearly explains what it does

### Test in Clean Environment

```bash
# Create fresh resource group
az group create --name test-scim-dist --location eastus

# Run deployment script
./deploy.sh

# Follow VALIDATION.md checklist
# Document any issues or unclear steps

# Clean up
az group delete --name test-scim-dist --yes
```

## FAQ for Customers

Include in customer communications:

**Q: How much does this cost?**
A: ~$1-2/month for typical usage (1000 user updates/month)

**Q: Can I customize the mappings?**
A: Yes! Use mapped mode with config/role-mapping.json

**Q: How do I update the Logic App?**
A: Redeploy using deploy.sh or update in Azure Portal

**Q: What if I have multiple environments?**
A: Deploy to separate resource groups for dev/test/prod

**Q: Is this officially supported by Nintex?**
A: Check with Nintex support for official stance. This is a community solution.

## Distribution Channels

### Internal Distribution

- Company wiki/knowledge base
- Internal GitHub/GitLab repository
- Shared network drive

### External Distribution

- Public GitHub repository
- Nintex/Promapp community forums
- Azure Marketplace (future consideration)

## Success Metrics

Track these to measure solution adoption:

- Number of deployments
- Customer feedback/satisfaction
- Support tickets (should be low)
- Feature requests
- Time to deployment (goal: <20 minutes)

---

## Quick Distribution Checklist

- [ ] Secrets removed
- [ ] Documentation reviewed and updated
- [ ] Repository URL added to docs
- [ ] Tested in clean environment
- [ ] Version tagged
- [ ] Release notes created
- [ ] Distribution package created (ZIP or repo)
- [ ] Customer handoff materials prepared

**Ready to distribute!** 🚀
