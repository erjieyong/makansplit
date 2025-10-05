# AWS Deployment Guide

This guide covers deploying the MakanSplit bot to AWS using Docker.

## Prerequisites

- AWS CLI configured with credentials
- Docker installed locally
- AWS account with appropriate permissions

## Deployment Options

### Option 1: AWS ECS/Fargate (Recommended)

**Advantages:**
- Fully managed, no server maintenance
- Auto-scaling capabilities
- Pay only for what you use
- Built-in health checks and restart policies

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
        },
        {
          "name": "PAYNOW_RECIPIENT_PHONE",
          "value": "+6512345678"
        },
        {
          "name": "PAYNOW_RECIPIENT_NAME",
          "value": "Your Name"
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

## Cost Estimates

### ECS Fargate
- CPU: 0.5 vCPU = $0.04048/hour
- Memory: 1 GB = $0.004445/hour
- **Total: ~$35/month** (24/7 operation)

### EC2 t3.micro
- Instance: $0.0104/hour
- **Total: ~$7.50/month** (24/7 operation)
- Storage: ~$1/month for 8GB

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

The bot is stateless except for:
- `user_pairings.json` - User-to-person mappings
- Recommendation: Mount EFS volume for persistent storage

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
