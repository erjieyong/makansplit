# AWS Deployment Guide

This guide covers deploying the MakanSplit bot to AWS using Docker.

## Prerequisites

- AWS CLI configured with credentials
- Docker installed locally
- AWS account with appropriate permissions

## Deployment Options

### Option 1: AWS App Runner (Easiest & Recommended)

**Advantages:**
- **Simplest AWS deployment option**
- Fully managed - no infrastructure management
- Automatic deployments from ECR or GitHub
- Built-in load balancing and auto-scaling
- Automatic HTTPS
- Pay only for what you use (~$25-30/month)

**Steps:**

#### 1. Create ECR Repository

```bash
aws ecr create-repository \
    --repository-name makansplit-bot \
    --region ap-southeast-1
```

#### 2. Build and Push Docker Image

```bash
# Login to ECR
aws ecr get-login-password --region ap-southeast-1 | \
docker login --username AWS --password-stdin \
YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com

# Build image
docker build -t makansplit-bot .

# Tag image
docker tag makansplit-bot:latest \
YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest

# Push to ECR
docker push \
YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest
```

#### 3. Create App Runner Service via AWS Console

1. Go to AWS App Runner console: https://console.aws.amazon.com/apprunner
2. Click **Create service**
3. **Source:**
   - Repository type: **Container registry**
   - Provider: **Amazon ECR**
   - Container image URI: `YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest`
   - Deployment trigger: **Manual** (or Automatic for CI/CD)
4. **Deployment settings:**
   - ECR access role: Create new or use existing with ECR permissions
5. **Service settings:**
   - Service name: `makansplit-bot`
   - CPU: **1 vCPU**
   - Memory: **2 GB**
   - Port: `8080` (not used, but required field)
   - Environment variables: Add your credentials
     ```
     TELEGRAM_BOT_TOKEN=your_token
     OPENROUTER_API_KEY=your_key
     OPENROUTER_MODEL=google/gemini-2.5-flash-lite-preview-09-2025
     ```
     Note: PayNow recipient info is now collected dynamically from users
6. **Auto scaling:**
   - Min instances: **1**
   - Max instances: **1** (bot doesn't need scaling)
7. **Health check:**
   - Protocol: **TCP** (since bot doesn't expose HTTP endpoint)
   - Interval: 10 seconds
8. Click **Create & deploy**

#### 4. Create App Runner Service via CLI (Alternative)

Create a file `apprunner.json`:

```json
{
  "ServiceName": "makansplit-bot",
  "SourceConfiguration": {
    "ImageRepository": {
      "ImageIdentifier": "YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "8080",
        "RuntimeEnvironmentVariables": {
          "TELEGRAM_BOT_TOKEN": "your_token",
          "OPENROUTER_API_KEY": "your_key",
          "OPENROUTER_MODEL": "google/gemini-2.5-flash-lite-preview-09-2025"
        }
      }
    },
    "AutoDeploymentsEnabled": false,
    "AuthenticationConfiguration": {
      "AccessRoleArn": "arn:aws:iam::YOUR_ACCOUNT_ID:role/AppRunnerECRAccessRole"
    }
  },
  "InstanceConfiguration": {
    "Cpu": "1 vCPU",
    "Memory": "2 GB"
  }
}
```

Deploy:

```bash
aws apprunner create-service --cli-input-json file://apprunner.json --region ap-southeast-1
```

#### 5. Monitor Deployment

```bash
# Check service status
aws apprunner list-services --region ap-southeast-1

# View service details
aws apprunner describe-service \
    --service-arn YOUR_SERVICE_ARN \
    --region ap-southeast-1

# View logs in CloudWatch
aws logs tail /aws/apprunner/makansplit-bot --follow
```

#### 6. Update App Runner Service

```bash
# Build and push new image (same as step 2)
docker build -t makansplit-bot .
docker tag makansplit-bot:latest YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest

# Trigger new deployment (if manual)
aws apprunner start-deployment \
    --service-arn YOUR_SERVICE_ARN \
    --region ap-southeast-1
```

### Option 2: AWS ECS/Fargate

**Advantages:**
- More control over infrastructure
- Better for complex deployments
- VPC networking control
- Lower cost for very small workloads (~$35/month)

**Steps:**

#### 1. Create ECR Repository

```bash
aws ecr create-repository \
    --repository-name makansplit-bot \
    --region ap-southeast-1
```

#### 2. Build and Push Docker Image

```bash
# Login to ECR
aws ecr get-login-password --region ap-southeast-1 | \
docker login --username AWS --password-stdin \
YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com

# Build image
docker build -t makansplit-bot .

# Tag image
docker tag makansplit-bot:latest \
YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest

# Push to ECR
docker push \
YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest
```

#### 3. Create ECS Task Definition

Create a file `task-definition.json`:

```json
{
  "family": "makansplit-bot",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "makansplit-bot",
      "image": "YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest",
      "essential": true,
      "environment": [
        {
          "name": "TELEGRAM_BOT_TOKEN",
          "value": "YOUR_BOT_TOKEN"
        },
        {
          "name": "OPENROUTER_API_KEY",
          "value": "YOUR_OPENROUTER_KEY"
        },
        {
          "name": "OPENROUTER_MODEL",
          "value": "google/gemini-2.5-flash-lite-preview-09-2025"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/makansplit-bot",
          "awslogs-region": "ap-southeast-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

**Using AWS Secrets Manager (Recommended):**

```json
{
  "secrets": [
    {
      "name": "TELEGRAM_BOT_TOKEN",
      "valueFrom": "arn:aws:secretsmanager:ap-southeast-1:ACCOUNT_ID:secret:makansplit/telegram-token"
    },
    {
      "name": "OPENROUTER_API_KEY",
      "valueFrom": "arn:aws:secretsmanager:ap-southeast-1:ACCOUNT_ID:secret:makansplit/openrouter-key"
    }
  ]
}
```

Register the task definition:

```bash
aws ecs register-task-definition \
    --cli-input-json file://task-definition.json
```

#### 4. Create ECS Cluster

```bash
aws ecs create-cluster \
    --cluster-name makansplit-cluster \
    --region ap-southeast-1
```

#### 5. Create CloudWatch Log Group

```bash
aws logs create-log-group \
    --log-group-name /ecs/makansplit-bot \
    --region ap-southeast-1
```

#### 6. Create ECS Service

```bash
aws ecs create-service \
    --cluster makansplit-cluster \
    --service-name makansplit-bot-service \
    --task-definition makansplit-bot \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=ENABLED}" \
    --region ap-southeast-1
```

**Note:** Replace `subnet-xxx` and `sg-xxx` with your VPC subnet and security group IDs.

Security group must allow:
- Outbound HTTPS (443) for Telegram API and AI providers
- Outbound HTTPS (443) for OpenRouter/Gemini API

#### 7. Monitor Deployment

```bash
# Check service status
aws ecs describe-services \
    --cluster makansplit-cluster \
    --services makansplit-bot-service

# View logs
aws logs tail /ecs/makansplit-bot --follow
```

### Option 2: AWS EC2

**Advantages:**
- Full control over the instance
- Lower cost for long-running bots
- Easier to debug

**Steps:**

#### 1. Launch EC2 Instance

- AMI: Ubuntu 22.04 LTS
- Instance Type: t3.small or t3.micro
- Security Group: Allow outbound HTTPS (443)
- Storage: 8GB minimum

#### 2. Connect and Install Docker

```bash
ssh -i your-key.pem ubuntu@your-ec2-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
sudo apt install docker.io docker-compose -y
sudo systemctl enable docker
sudo systemctl start docker

# Add user to docker group
sudo usermod -aG docker ubuntu
```

#### 3. Deploy the Bot

```bash
# Clone repository (or upload files)
git clone https://github.com/yourusername/makansplit.git
cd makansplit

# Create .env file
nano .env
# Add your credentials

# Start the bot
docker-compose up -d

# View logs
docker-compose logs -f
```

#### 4. Set Up Auto-Restart

```bash
# Edit docker-compose.yml to include restart policy
docker-compose up -d

# Or use systemd service
sudo nano /etc/systemd/system/makansplit.service
```

Add:

```ini
[Unit]
Description=MakanSplit Telegram Bot
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/ubuntu/makansplit
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
User=ubuntu

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl enable makansplit
sudo systemctl start makansplit
```

## Cost Comparison (Singapore ap-southeast-1 Region)

### AWS App Runner (Recommended)
**Configuration:** 1 vCPU, 2 GB RAM, 1 instance

**Pricing Breakdown:**
- **Provisioned container:** $0.007/hour = $5.04/month
- **Active container:** $0.064/vCPU-hour + $0.007/GB-hour
  - vCPU: $0.064 × 1 × 730 hours = $46.72/month
  - Memory: $0.007 × 2 × 730 hours = $10.22/month
- **Build:** $0.005/build minute (only if building from source)

**Total: ~$62/month (24/7 operation)**

**Advantages:**
- ✅ Zero infrastructure management
- ✅ Automatic scaling (if needed)
- ✅ Built-in load balancer
- ✅ Auto-deployments from ECR/GitHub
- ✅ Automatic HTTPS
- ❌ Higher cost

### ECS Fargate
**Configuration:** 0.5 vCPU, 1 GB RAM

**Pricing Breakdown:**
- vCPU: $0.04048/vCPU-hour × 0.5 × 730 hours = $14.78/month
- Memory: $0.004445/GB-hour × 1 × 730 hours = $3.24/month

**Total: ~$18/month (24/7 operation)**

**With 1 vCPU, 2 GB RAM:**
- vCPU: $0.04048 × 1 × 730 = $29.55/month
- Memory: $0.004445 × 2 × 730 = $6.49/month
- **Total: ~$36/month**

**Advantages:**
- ✅ More control over infrastructure
- ✅ VPC networking
- ✅ Lower cost than App Runner
- ✅ Good for multiple services
- ❌ More complex setup
- ❌ Need to manage ECS cluster

### EC2 t3.micro
**Configuration:** 2 vCPU, 1 GB RAM

**Pricing Breakdown:**
- Instance: $0.0104/hour × 730 hours = $7.59/month
- Storage (8GB EBS): $0.10/GB-month × 8 = $0.80/month
- Data transfer: ~$1-2/month

**Total: ~$9-10/month (24/7 operation)**

**Advantages:**
- ✅ Lowest cost option
- ✅ Full server control
- ✅ Good for learning/testing
- ❌ Need to manage OS updates
- ❌ Manual scaling
- ❌ No auto-restart (need systemd)

### EC2 t4g.micro (ARM-based, even cheaper!)
**Configuration:** 2 vCPU, 1 GB RAM

**Pricing Breakdown:**
- Instance: $0.0084/hour × 730 hours = $6.13/month
- Storage: $0.80/month
- Data transfer: ~$1-2/month

**Total: ~$8-9/month (24/7 operation)**

**Note:** Requires ARM-compatible Docker image (slight Dockerfile change)

## Cost Comparison Summary

| Option | Monthly Cost | Complexity | Management | Best For |
|--------|--------------|------------|------------|----------|
| **App Runner** | **$62** | ⭐ Easy | Zero | Production, hands-off |
| **ECS Fargate** | **$18-36** | ⭐⭐ Medium | Low | Production, AWS native |
| **EC2 t3.micro** | **$9-10** | ⭐⭐⭐ Hard | High | Budget, learning |
| **EC2 t4g.micro** | **$8-9** | ⭐⭐⭐ Hard | High | Cheapest option |

## Recommendation by Use Case

### 🚀 Production (Hands-off)
**→ AWS App Runner**
- Worth the extra cost for zero management
- Automatic deployments
- Built-in monitoring and scaling

### 💼 Production (Cost-conscious)
**→ ECS Fargate (0.5 vCPU, 1 GB)**
- Best price/performance ratio at $18/month
- Managed service with some AWS control
- Easy to scale if needed

### 💰 Budget/Testing
**→ EC2 t3.micro or t4g.micro**
- Extremely cheap at $8-10/month
- Good for learning and testing
- Requires more manual management

### ⚡ Current Running Bot
Since your bot is already running locally, **App Runner or ECS Fargate** are recommended for production to avoid server maintenance.

## Monitoring and Maintenance

### CloudWatch Alarms (ECS)

```bash
# CPU utilization alarm
aws cloudwatch put-metric-alarm \
    --alarm-name makansplit-high-cpu \
    --alarm-description "Alert when CPU exceeds 80%" \
    --metric-name CPUUtilization \
    --namespace AWS/ECS \
    --statistic Average \
    --period 300 \
    --threshold 80 \
    --comparison-operator GreaterThanThreshold \
    --evaluation-periods 2
```

### Log Monitoring

```bash
# View recent logs
aws logs tail /ecs/makansplit-bot --since 1h

# Follow logs in real-time
aws logs tail /ecs/makansplit-bot --follow
```

### Updating the Bot

```bash
# Build and push new image
docker build -t makansplit-bot .
docker tag makansplit-bot:latest YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.ap-southeast-1.amazonaws.com/makansplit-bot:latest

# Update ECS service (force new deployment)
aws ecs update-service \
    --cluster makansplit-cluster \
    --service makansplit-bot-service \
    --force-new-deployment
```

## Troubleshooting

### Bot not responding

```bash
# Check ECS task status
aws ecs list-tasks --cluster makansplit-cluster
aws ecs describe-tasks --cluster makansplit-cluster --tasks TASK_ARN

# Check logs
aws logs tail /ecs/makansplit-bot --since 30m
```

### High memory usage

- Increase task memory in task definition
- Check for photo file cleanup in `temp_photos/`

### API rate limits

- Monitor CloudWatch logs for rate limit errors
- Consider implementing exponential backoff
- Switch to higher tier AI provider plan if needed

## Security Best Practices

1. **Use AWS Secrets Manager** for sensitive credentials
2. **Enable VPC Flow Logs** for network monitoring
3. **Regular updates**: Update base Docker image monthly
4. **Least privilege**: Use IAM roles with minimal permissions
5. **Enable CloudTrail** for audit logging

## Backup Strategy

The bot maintains persistent state in:
- `user_pairings.json` - Person-to-Telegram-user mappings for Photo AI mode
- `user_paynow.json` - User PayNow recipient information (phone + name)

Recommendation: Mount EFS volume for persistent storage

```bash
# Create EFS filesystem
aws efs create-file-system --region ap-southeast-1

# Mount in task definition
{
  "mountPoints": [{
    "sourceVolume": "efs-storage",
    "containerPath": "/app/data"
  }]
}
```

## Rolling Back

```bash
# List task definition revisions
aws ecs list-task-definitions --family-prefix makansplit-bot

# Update service to previous revision
aws ecs update-service \
    --cluster makansplit-cluster \
    --service makansplit-bot-service \
    --task-definition makansplit-bot:PREVIOUS_REVISION
```
