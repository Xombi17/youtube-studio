#!/usr/bin/env python3
"""
CreatorRadar / ClipSurge — Automated End-to-End AWS 24/7 Cloud Deployment

Deploys the full clipping studio on an AWS EC2 instance in ap-southeast-2:
1. Creates security group 'clipsurge-studio-sg' (SSH 22, Web UI 3000, API 8080).
2. Generates SSH key pair 'clipsurge-studio-key' and saves ~/.ssh/clipsurge-studio-key.pem.
3. Automatically embeds local API keys & YouTube OAuth tokens into Cloud-Init.
4. Launches an Ubuntu 24.04 LTS instance (t3.medium, 40GB gp3 SSD).
5. Waits for initialization, outputs Public IP, Web Dashboard URL, and SSH command.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = STUDIO_ROOT / "config"
REGION = "ap-southeast-2"
AMI_ID = "ami-0b13e37fa8d8689c3"  # Ubuntu 24.04 LTS Noble in ap-southeast-2
INSTANCE_TYPE = "t3.small"         # Free Tier eligible (2 vCPU, 2GB RAM + 4GB swap)
KEY_NAME = "clipsurge-studio-key"
KEY_FILE = Path(os.path.expanduser(f"~/.ssh/{KEY_NAME}.pem"))
SG_NAME = "clipsurge-studio-sg"


def run_cmd(cmd: str) -> str:
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\nError: {res.stderr.strip()}")
    return res.stdout.strip()


def get_default_vpc_and_subnet() -> tuple[str, str]:
    vpcs_raw = run_cmd(f"aws ec2 describe-vpcs --filters Name=isDefault,Values=true --region {REGION}")
    vpcs = json.loads(vpcs_raw).get("Vpcs", [])
    if not vpcs:
        raise RuntimeError(f"No default VPC found in {REGION}")
    vpc_id = vpcs[0]["VpcId"]

    subnets_raw = run_cmd(f"aws ec2 describe-subnets --filters Name=vpc-id,Values={vpc_id} --region {REGION}")
    subnets = json.loads(subnets_raw).get("Subnets", [])
    if not subnets:
        raise RuntimeError(f"No subnets found for VPC {vpc_id} in {REGION}")
    subnet_id = subnets[0]["SubnetId"]
    return vpc_id, subnet_id


def ensure_key_pair() -> None:
    keys_raw = run_cmd(f"aws ec2 describe-key-pairs --region {REGION}")
    keys = [k["KeyName"] for k in json.loads(keys_raw).get("KeyPairs", [])]
    if KEY_NAME in keys:
        print(f"  [SSH] Key pair '{KEY_NAME}' already exists on AWS.")
        if not KEY_FILE.exists():
            print(f"  [SSH] Local file {KEY_FILE} is missing. Replacing key pair...")
            run_cmd(f"aws ec2 delete-key-pair --key-name {KEY_NAME} --region {REGION}")
        else:
            return

    print(f"  [SSH] Creating key pair '{KEY_NAME}'...")
    res = run_cmd(f"aws ec2 create-key-pair --key-name {KEY_NAME} --query 'KeyMaterial' --output text --region {REGION}")
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(res, encoding="utf-8")
    os.chmod(KEY_FILE, 0o400)
    print(f"  [SSH] Saved private key to {KEY_FILE}")


def ensure_security_group(vpc_id: str) -> str:
    sgs_raw = run_cmd(f"aws ec2 describe-security-groups --filters Name=group-name,Values={SG_NAME} --region {REGION}")
    sgs = json.loads(sgs_raw).get("SecurityGroups", [])
    if sgs:
        sg_id = sgs[0]["GroupId"]
        print(f"  [SecurityGroup] Using existing group {sg_id} ({SG_NAME})")
        return sg_id

    print(f"  [SecurityGroup] Creating security group '{SG_NAME}' in VPC {vpc_id}...")
    sg_res = run_cmd(f"aws ec2 create-security-group --group-name {SG_NAME} --description 'ClipSurge 24/7 Studio Ports' --vpc-id {vpc_id} --region {REGION}")
    sg_id = json.loads(sg_res)["GroupId"]

    rules = [
        {"IpProtocol": "tcp", "FromPort": 22, "ToPort": 22, "CidrIp": "0.0.0.0/0"},      # SSH
        {"IpProtocol": "tcp", "FromPort": 3000, "ToPort": 3000, "CidrIp": "0.0.0.0/0"},  # Next.js UI
        {"IpProtocol": "tcp", "FromPort": 8080, "ToPort": 8080, "CidrIp": "0.0.0.0/0"},  # Studio API
    ]
    for r in rules:
        cmd = f"aws ec2 authorize-security-group-ingress --group-id {sg_id} --protocol {r['IpProtocol']} --port {r['FromPort']} --cidr {r['CidrIp']} --region {REGION}"
        subprocess.run(cmd, shell=True, capture_output=True)

    print(f"  [SecurityGroup] Configured ports 22, 3000, 8080 on {sg_id}")
    return sg_id


def build_user_data() -> str:
    dotenv_p = STUDIO_ROOT / ".env"
    dotenv_content = dotenv_p.read_text(encoding="utf-8") if dotenv_p.exists() else ""

    token_p = CONFIG_DIR / "youtube_token_clipper.json"
    token_content = token_p.read_text(encoding="utf-8") if token_p.exists() else "{}"

    secret_p = CONFIG_DIR / "youtube_client_secret_clipper.json"
    secret_content = secret_p.read_text(encoding="utf-8") if secret_p.exists() else "{}"

    script = f"""#!/bin/bash
set -e
exec > >(tee -a /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1

echo "=== [ClipSurge] Initializing Cloud Instance ==="

# 0. Setup 4GB Swap space to guarantee smooth npm build on 2GB RAM
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=4096
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 1. Update and install base packages
apt-get update
apt-get install -y ca-certificates curl gnupg git ffmpeg python3-pip

# 2. Install Docker
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3. Setup Project Directory
mkdir -p /home/ubuntu/youtube-studio
cd /home/ubuntu
git clone https://github.com/Xombi17/youtube-studio.git youtube-studio
cd youtube-studio

# 4. Inject Environment & Credentials
cat << 'EOF_DOTENV' > .env
{dotenv_content}
EOF_DOTENV

mkdir -p config
cat << 'EOF_TOKEN' > config/youtube_token_clipper.json
{token_content}
EOF_TOKEN
chmod 600 config/youtube_token_clipper.json

cat << 'EOF_SECRET' > config/youtube_client_secret_clipper.json
{secret_content}
EOF_SECRET
chmod 600 config/youtube_client_secret_clipper.json

# 5. Fix permissions
chown -R ubuntu:ubuntu /home/ubuntu/youtube-studio
usermod -aG docker ubuntu

# 6. Build and start containers
echo "=== [ClipSurge] Building and Starting Studio Containers ==="
docker compose up -d --build

echo "=== [ClipSurge] Cloud Init Complete! ==="
"""
    return script


def launch_instance():
    print("=" * 64)
    print(" 🚀 Launching ClipSurge 24/7 Studio on AWS EC2 (ap-southeast-2)")
    print(f" • Instance Type: {INSTANCE_TYPE} (2 vCPU, 4GB RAM)")
    print(f" • OS:            Ubuntu 24.04 LTS ({AMI_ID})")
    print(f" • Storage:       40 GB gp3 SSD")
    print("=" * 64)

    vpc_id, subnet_id = get_default_vpc_and_subnet()
    print(f"  [VPC] Using default VPC {vpc_id}, Subnet {subnet_id}")

    ensure_key_pair()
    sg_id = ensure_security_group(vpc_id)

    user_data = build_user_data()
    tmp_ud = Path("/tmp/clipsurge_userdata.sh")
    tmp_ud.write_text(user_data, encoding="utf-8")

    block_spec = [
        {
            "DeviceName": "/dev/sda1",
            "Ebs": {
                "VolumeSize": 40,
                "VolumeType": "gp3",
                "DeleteOnTermination": True,
            },
        }
    ]
    block_json = json.dumps(block_spec)

    print("  [EC2] Spawning instance...")
    cmd = (
        f"aws ec2 run-instances "
        f"--image-id {AMI_ID} "
        f"--instance-type {INSTANCE_TYPE} "
        f"--key-name {KEY_NAME} "
        f"--security-group-ids {sg_id} "
        f"--subnet-id {subnet_id} "
        f"--associate-public-ip-address "
        f"--block-device-mappings '{block_json}' "
        f"--user-data file://{tmp_ud} "
        f"--tag-specifications 'ResourceType=instance,Tags=[{{Key=Name,Value=ClipSurge-24-7-Studio}}]' "
        f"--region {REGION}"
    )
    res_raw = run_cmd(cmd)
    data = json.loads(res_raw)
    inst_id = data["Instances"][0]["InstanceId"]
    print(f"  [EC2] Instance created: {inst_id}")
    print("  [EC2] Waiting for instance to enter RUNNING state...")

    run_cmd(f"aws ec2 wait instance-running --instance-ids {inst_id} --region {REGION}")

    desc_raw = run_cmd(f"aws ec2 describe-instances --instance-ids {inst_id} --region {REGION}")
    inst_info = json.loads(desc_raw)["Reservations"][0]["Instances"][0]
    public_ip = inst_info.get("PublicIpAddress", "N/A")
    public_dns = inst_info.get("PublicDnsName", "N/A")

    print("\n" + "=" * 64)
    print(" 🎉 AWS EC2 INSTANCE IS LIVE!")
    print("=" * 64)
    print(f" • Instance ID:  {inst_id}")
    print(f" • Region:       {REGION}")
    print(f" • Public IP:    {public_ip}")
    print(f" • Web Studio:   http://{public_ip}:3000")
    print(f" • Studio API:   http://{public_ip}:8080")
    print(f" • SSH Command:  ssh -i {KEY_FILE} ubuntu@{public_ip}")
    print("=" * 64)
    print("Note: Docker build and container startup take ~3 minutes on first boot.")
    print("You can view progress with:")
    print(f"  ssh -i {KEY_FILE} ubuntu@{public_ip} 'tail -f /var/log/user-data.log'")
    print("=" * 64)


if __name__ == "__main__":
    launch_instance()
