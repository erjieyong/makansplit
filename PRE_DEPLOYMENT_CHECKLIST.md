# Pre-Deployment Checklist

## ✅ Version Control Ready
- [x] Git repository initialized
- [x] All changes committed
- [x] .env excluded from version control
- [x] .env.example created with all required variables
- [x] Documentation complete (README, CLAUDE.md, DEPLOYMENT.md)

## 🔐 Credentials Setup

Before deploying, ensure you have:

- [ ] **Telegram Bot Token** (from @BotFather)
- [ ] **AI Provider API Key**:
  - [ ] Gemini API Key (from Google AI Studio), OR
  - [ ] OpenRouter API Key (from openrouter.ai)
- [ ] **PayNow Details**:
  - [ ] Singapore phone number (+6512345678)
  - [ ] Recipient name

## 🐳 Docker Verification

Test locally before deploying:

```bash
# 1. Build the image
docker build -t makansplit-bot .

# 2. Test run (with .env file)
docker-compose up

# 3. Verify bot responds in Telegram
# Send /start to your bot

# 4. Stop the test
docker-compose down
```

## ☁️ AWS Prerequisites

### For ECS/Fargate:
- [ ] AWS CLI installed and configured
- [ ] AWS account with permissions for:
  - [ ] ECR (Elastic Container Registry)
  - [ ] ECS (Elastic Container Service)
  - [ ] CloudWatch Logs
  - [ ] Secrets Manager (optional but recommended)
- [ ] VPC with subnets configured
- [ ] Security group allowing outbound HTTPS (443)

### For EC2:
- [ ] EC2 key pair created
- [ ] Security group configured (outbound HTTPS)
- [ ] SSH access configured

## 🚀 Deployment Steps

Choose your deployment method from DEPLOYMENT.md:

### Option 1: ECS/Fargate (Recommended)
1. Create ECR repository
2. Build and push Docker image
3. Create CloudWatch log group
4. Create/register ECS task definition
5. Create ECS cluster
6. Create ECS service
7. Monitor logs

### Option 2: EC2
1. Launch EC2 instance
2. Install Docker
3. Clone/upload repository
4. Create .env file
5. Run docker-compose
6. Set up auto-restart

## 📊 Post-Deployment Verification

- [ ] Bot is online in Telegram
- [ ] Send /start - bot responds
- [ ] Upload test bill photo - analysis works
- [ ] Test all three split modes:
  - [ ] Even split
  - [ ] Manual split
  - [ ] Photo AI split
- [ ] Verify PayNow QR codes generate correctly
- [ ] Check CloudWatch logs (if using AWS)

## 🔍 Monitoring Setup

- [ ] CloudWatch alarms configured (CPU, Memory)
- [ ] Log monitoring active
- [ ] Cost alerts set up
- [ ] Backup strategy implemented (if needed)

## 🛡️ Security Review

- [ ] .env file not committed
- [ ] API keys stored in Secrets Manager (AWS) or secure .env
- [ ] Security group rules reviewed
- [ ] IAM permissions follow least privilege
- [ ] Docker image scanned for vulnerabilities

## 💰 Cost Estimate

**ECS Fargate (0.5 vCPU, 1GB RAM):**
- ~$35/month for 24/7 operation

**EC2 t3.micro:**
- ~$7.50/month for 24/7 operation

## 📝 Notes

- Bot uses **long polling** (no webhook), so no load balancer needed
- Recommended: 512 CPU units, 1GB memory minimum
- Temp photos stored in `temp_photos/` directory
- User pairings stored in `user_pairings.json`

## 🆘 Troubleshooting Resources

If deployment fails, check:
1. DEPLOYMENT.md - Detailed deployment guide
2. CLAUDE.md - Architecture and design patterns
3. README.md - Basic setup and usage
4. CloudWatch Logs - Runtime errors
5. `docker-compose logs -f` - Local debugging

## 📞 Support

For issues:
1. Check logs first
2. Verify all environment variables
3. Test locally with Docker before deploying
4. Review DEPLOYMENT.md troubleshooting section
