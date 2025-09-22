<div align="center">
  <img src="assets/logo.svg" alt="CloudVault Logo" width="200" height="200">
  
# CloudVault - AWS S3 Bucket Scanner & Cloud Security Tool

**🔍 Find exposed AWS S3 buckets, Google Cloud Storage & Azure Blob containers with advanced vulnerability detection**

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE) 
[![Security Scanner](https://img.shields.io/badge/security-scanner-red)](https://github.com/ibrahmsql/CloudVault)
[![S3 Bucket Scanner](https://img.shields.io/badge/S3-bucket%20scanner-orange)](https://github.com/ibrahmsql/CloudVault)
[![Cloud Security](https://img.shields.io/badge/cloud-security%20tool-purple)](https://github.com/ibrahmsql/CloudVault)

</div>

---

## 🎯 AWS S3 Bucket Scanner | Cloud Security Scanner | Bucket Enumeration Tool

**CloudVault** is a powerful **AWS S3 bucket scanner**, **Google Cloud Storage enumeration tool**, and **Azure Blob vulnerability scanner**. Discover exposed cloud storage buckets, detect security misconfigurations, and identify vulnerabilities across AWS S3, GCP Storage, and Azure Blob containers through real-time certificate transparency monitoring.



## 🚀 Why Choose CloudVault?

> **The AWS S3 Bucket Scanner for Cloud Security Professionals**

CloudVault is the most comprehensive **cloud storage security scanner** available, designed for penetration testers, bug bounty hunters, and security researchers. Our tool monitors certificate transparency logs in real-time to discover publicly accessible cloud storage buckets across **AWS S3**, **Google Cloud Storage**, and **Azure Blob Storage**.

### 🎯 Perfect For:
- **Bug Bounty Hunters** - Find exposed S3 buckets and cloud storage misconfigurations
- **Penetration Testers** - Comprehensive cloud security assessment toolkit  
- **Security Researchers** - Advanced OSINT and reconnaissance capabilities
- **DevSecOps Teams** - Continuous cloud security monitoring
- **Cybersecurity Professionals** - Enterprise-grade vulnerability scanning

## ✨ Core Features - S3 Bucket Scanner & Cloud Security Tools

### 🌐 AWS S3 & Multi-Cloud Bucket Discovery
- **AWS S3 Bucket Scanner** - Find exposed S3 buckets with authenticated & unauthenticated access
- **Google Cloud Storage Scanner** - Comprehensive GCS bucket enumeration and vulnerability detection
- **Azure Blob Storage Scanner** - Advanced container discovery with account enumeration
- **Multi-Cloud Support** - Simultaneous scanning across all major cloud providers

### 🔄 Real-time Certificate Transparency Monitoring
- **Live CT Log Monitoring** - Real-time domain discovery for immediate bucket scanning
- **WebSocket Integration** - Async connections with automatic reconnection capabilities
- **Domain Intelligence** - Advanced domain extraction and bucket name permutation
- **Zero-Day Discovery** - Find newly registered domains and their associated buckets

### 🧠 Intelligent S3 Bucket Enumeration
- **Smart Permutation Engine** - Advanced bucket name generation with provider-specific rules
- **Keyword-Based Detection** - Identify sensitive content and interesting files automatically
- **Rate Limit Evasion** - Built-in quota management and intelligent throttling
- **Custom Wordlists** - Support for custom dictionary-based bucket enumeration

### 📋 Enterprise Security Reporting
- **Detailed Vulnerability Reports** - Comprehensive security assessment documentation
- **Multi-Format Output** - JSON, CSV, and structured logging capabilities
- **Slack Integration** - Real-time notifications for critical findings
- **Executive Dashboards** - High-level security metrics and progress tracking

## 🚀 Quick Start - Install AWS S3 Bucket Scanner

### 📦 Installation Options

```bash
# Install CloudVault - Complete S3 Bucket Scanner
pip install cloudvault

# Full installation with all cloud providers (AWS S3, GCP, Azure)
pip install cloudvault[all]

# Provider-specific installations for targeted scanning
pip install cloudvault[aws]      # AWS S3 bucket scanner only
pip install cloudvault[gcp]      # Google Cloud Storage scanner only  
pip install cloudvault[azure]    # Azure Blob Storage scanner only

# Security researcher edition with all exploitation features
pip install cloudvault[full]
```

### 🎧 Basic S3 Bucket Scanning Usage

```bash
# Initialize CloudVault configuration
cloudvault --init-config

# Start real-time S3 bucket discovery via certificate transparency
cloudvault

# Scan specific domains for S3 buckets and cloud storage
cloudvault --source target-domains.txt

# AWS S3 bucket scanner mode only
cloudvault --aws-only

# Find only interesting/sensitive buckets
cloudvault --only-interesting

# Advanced S3 vulnerability scanning
cloudvault --scan-vulnerabilities --download-content
```

### 🔍 Advanced Cloud Security Scanning

```bash
# Stealth mode S3 bucket scanning (avoid detection)
cloudvault --stealth --proxy-rotation --anti-forensics

# Comprehensive security assessment
cloudvault --metadata-extraction --stego-detection --subdomain-takeover

# Database credential testing with custom wordlist
cloudvault --database-testing --db-wordlist passwords.txt

# Network pivoting and lateral movement
cloudvault --network-pivoting --credential-harvesting
```

## ⚙️ Configuration

The tool uses a YAML configuration file (`config.yaml`) for all settings:

```yaml
# General Settings
queue_size: 1000
update_interval: 30
log_level: INFO

# AWS S3 Configuration
aws:
  enabled: true
  access_key: 'YOUR_ACCESS_KEY'
  secret_key: 'YOUR_SECRET_KEY'
  region: us-east-1
  max_threads: 20

# Google Cloud Storage Configuration
gcp:
  enabled: true
  service_account_path: '/path/to/service-account.json'
  project_id: 'your-project-id'
  max_threads: 15

# Azure Blob Storage Configuration
azure:
  enabled: true
  account_name: 'your-storage-account'
  account_key: 'YOUR_ACCOUNT_KEY'
  max_threads: 15
```

### Environment Variables

You can also use environment variables instead of storing credentials in the config:

```bash
# AWS
export AWS_ACCESS_KEY_ID="your_access_key"
export AWS_SECRET_ACCESS_KEY="your_secret_key"

# Google Cloud
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
export GOOGLE_CLOUD_PROJECT="your-project-id"

# Azure
export AZURE_STORAGE_ACCOUNT="your_account_name"
export AZURE_STORAGE_KEY="your_account_key"
```

## 📋 Command Line Options

```
cloudvault [OPTIONS]

Configuration:
  -c, --config FILE         Configuration file path (default: config.yaml)
  --init-config            Create a default configuration file

Input:
  -s, --source FILE        Process static domain list instead of live stream
  -p, --permutations FILE  Custom permutation patterns file
  --keywords-file FILE     Keywords for interesting content detection

Workers:
  -t, --threads N          Override number of worker threads per provider

Filtering:
  --only-interesting       Only report buckets with interesting content
  --skip-lets-encrypt      Skip Let's Encrypt certificates

Output:
  -l, --log-to-file        Log found buckets to file
  -v, --verbose            Enable verbose logging

Providers:
  --aws-only              Only check AWS S3 buckets
  --gcp-only              Only check Google Cloud Storage buckets
  --azure-only            Only check Azure Blob Storage containers

Advanced Features:
  --stealth               Enable stealth mode with evasion techniques
  --scan-vulnerabilities  Perform vulnerability scanning on discovered buckets
  --download-content      Download and analyze bucket contents
  --dns-enum             Enable DNS-based bucket enumeration
  --db-wordlist FILE     Use wordlist for database credential testing
  
Stealth Options:
  --proxy-rotation        Enable proxy rotation for anonymity
  --traffic-shaping TYPE  Shape traffic (mobile/residential/datacenter)
  --geo-country CODE      Simulate traffic from specific country
  --anti-forensics       Enable anti-forensics and evidence cleanup
  --process-masking      Hide process from monitoring tools

Security Analysis:
  --metadata-extraction   Extract metadata from discovered files
  --stego-detection      Scan for steganography in images and files
  --subdomain-takeover   Check for subdomain takeover vulnerabilities
  --database-testing     Test databases with default/weak credentials
  --network-pivoting     Attempt lateral movement with found credentials
```

## 🎯 Example Output

```
Starting CloudVault .0
Providers: aws, gcp, azure | Workers: 50 | Patterns: 127

Connected to certificate transparency stream!

Found AWS bucket: https://company-backup.s3.amazonaws.com [PUBLIC_READ] (Owner: company-admin) - 3 interesting files!
Found GCP bucket: https://storage.googleapis.com/company-logs [PUBLIC_READ]
Found AZURE container: https://companydata.blob.core.windows.net/backups [PRIVATE]

Status: 1,247 checked (42.3/s), 3 found, 2 public, 1 interesting
  aws: 856 checked, 2 found, 1 public
  gcp: 234 checked, 1 found, 1 public
  azure: 157 checked, 0 found, 0 public
```

## 🔧 Advanced Usage

### Custom Permutation Patterns

Create custom bucket name patterns in `permutations/custom.txt`:

```
{domain}-backup
{domain}-data
{domain}-storage
backup-{domain}
data-{domain}
{domain}001
{domain}prod
```

### Keywords for Interesting Content

Define keywords in `keywords.txt` to identify sensitive files:

```
password
config
secret
backup
.sql
.env
credentials
private
```

### Slack Integration

Add your Slack webhook URL to the configuration for real-time notifications:

```yaml
slack_webhook: 'https://hooks.slack.com/services/YOUR/WEBHOOK/URL'
```

## 🏗️ Architecture

CloudVault follows a modern, modular architecture:

```
cloudvault_discovery/
├── core/                 # Core functionality
│   ├── config.py        # Configuration management
│   ├── cert_stream.py   # Certificate transparency monitoring
│   ├── queue_manager.py # Thread-safe queue management
│   ├── worker.py        # Base worker classes
│   └── permutations.py  # Bucket name generation
├── providers/           # Cloud provider implementations
│   ├── aws_s3.py       # AWS S3 support
│   ├── gcp_storage.py  # Google Cloud Storage support
│   └── azure_blob.py   # Azure Blob Storage support
└── cli.py              # Command-line interface
```

### Key Components

- **Certificate Stream Monitor**: Async WebSocket client for real-time CT log monitoring
- **Queue Manager**: Thread-safe, provider-specific queues with rate limiting
- **Provider Workers**: Modular cloud storage implementations with authentication
- **Permutation Generator**: Smart bucket name generation from domains
- **Result Handler**: Unified output formatting and logging

## 🛡️ Security Considerations

### Responsible Disclosure
This tool is designed for security research and authorized testing only. Always ensure you have permission before testing against any infrastructure.

### Rate Limiting
- Built-in rate limiting for all cloud providers
- Exponential backoff for rate limit responses
- Configurable request delays and timeouts

### Authentication
- Supports both authenticated and unauthenticated modes
- Higher thread limits and better access control detection when authenticated
- Secure credential handling via environment variables

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/ibrahmsql/CloudVault.git
cd cloudvault

# Install in development mode with all dependencies
pip install -e .[dev,all]

# Run tests
pytest

# Format code
black cloudvault_discovery/

# Type checking
mypy cloudvault_discovery/
```

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Certificate Transparency community for their excellent work
- Cloud security research community
- Open source security tools ecosystem

## ⚠️ Disclaimer

This tool is for educational and authorized security research purposes only. Users are responsible for complying with applicable laws and regulations. The authors are not responsible for any misuse or damage caused by this tool.


<div align="center">

**⭐ Star this repository if CloudVault helped you find S3 buckets!**

[![GitHub stars](https://img.shields.io/github/stars/ibrahmsql/CloudVault?style=social)](https://github.com/ibrahmsql/CloudVault)

**Made with ❤️ by ibrahimsql**

</div>
