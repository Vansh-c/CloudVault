# 🚀 CloudVault Release Automation

Bu dokümantasyon CloudVault projesi için otomatik release sürecini açıklar.

## ⚙️ Kurulum

### 1. GitHub Secrets Ekleme

GitHub repository'nizde aşağıdaki secrets'ları ekleyin:

```bash
# PyPI API Token (ana release için)
PYPI_API_TOKEN=pypi-xxx...

# Test PyPI API Token (test için)
TEST_PYPI_API_TOKEN=pypi-xxx...
```

### 2. PyPI Token Alma

1. [PyPI Account Settings](https://pypi.org/manage/account/) → API tokens
2. "Add API token" → "Entire account" scope seçin
3. Token'ı kopyalayın ve GitHub secrets'a ekleyin

## 🎯 Release Süreçleri

### Method 1: Otomatik Script ile (Önerilen)

```bash
# Patch version bump (1.0.0 → 1.0.1)
./scripts/release.sh 1.0.1 "Bug fixes and improvements"

# Minor version bump (1.0.1 → 1.1.0)  
./scripts/release.sh 1.1.0 "New features added"

# Major version bump (1.1.0 → 2.0.0)
./scripts/release.sh 2.0.0 "Breaking changes and new architecture"
```

### Method 2: Manual Git Tag

```bash
# Version'ı manuel olarak güncelle
./scripts/version.py bump --type patch

# Git işlemleri
git add .
git commit -m "Release v1.0.1"
git tag -a v1.0.1 -m "Release v1.0.1"
git push origin main
git push origin v1.0.1
```

### Method 3: GitHub UI üzerinden

1. GitHub → Releases → "Create a new release"
2. Tag version: `v1.0.1` 
3. Release title: `CloudVault v1.0.1`
4. Description: Release notes
5. "Publish release"

## 🔄 Otomatik Pipeline

Tag push edildiğinde otomatik olarak:

1. ✅ **Build Test**: Package build edilir ve test edilir
2. ✅ **Installation Test**: Pip install test edilir
3. ✅ **CLI Test**: `cloudvault --help` çalıştırılır
4. ✅ **Test PyPI**: Test PyPI'a publish edilir (tag push)
5. ✅ **PyPI Release**: Ana PyPI'a publish edilir (GitHub release)
6. ✅ **Release Notes**: Otomatik release notes oluşturulur

## 📋 Version Management

```bash
# Mevcut version'ı görüntüle
./scripts/version.py show

# Version bump (dry-run)
./scripts/version.py bump --type patch --dry-run

# Version bump (gerçek)
./scripts/version.py bump --type minor

# Belirli version set et
./scripts/version.py set --version 1.2.0
```

## 📁 Dosya Yapısı

```
CloudVault/
├── .github/workflows/
│   └── release.yml              # GitHub Actions workflow
├── scripts/
│   ├── release.sh               # Otomatik release script
│   └── version.py               # Version management
├── pyproject.toml               # Package configuration
└── cloudvault_discovery/
    └── __init__.py              # Version definition
```

## 🐛 Sorun Giderme

### Release başarısız olursa:

1. **Build hatası**: Local'de `python -m build` test edin
2. **PyPI hatası**: Token'ların doğru olduğunu kontrol edin
3. **Version conflict**: Aynı version tekrar yüklenmez

### Manual cleanup:

```bash
# Local build dosyalarını temizle
rm -rf dist/ build/ *.egg-info/

# Git tag silme (gerekirse)
git tag -d v1.0.1
git push origin --delete v1.0.1
```

## 📈 Release Checklist

- [ ] Code review tamamlandı
- [ ] Tests passed
- [ ] Documentation updated
- [ ] Version bumped
- [ ] CHANGELOG.md updated
- [ ] Tag created ve pushed
- [ ] GitHub Actions success
- [ ] PyPI package available
- [ ] Installation test: `pip install cloudvault4==x.x.x`

## 🎉 Release Examples

### Patch Release (Bug Fixes)
```bash
./scripts/release.sh 1.0.1 "🐛 Fixed bucket permission detection bug"
```

### Minor Release (New Features)
```bash
./scripts/release.sh 1.1.0 "✨ Added Azure Blob Storage support and stealth mode"
```

### Major Release (Breaking Changes)
```bash
./scripts/release.sh 2.0.0 "🚀 Complete rewrite with new architecture and breaking API changes"
```

Her release sonrasında:
- 📦 [PyPI Package](https://pypi.org/project/cloudvault4/)
- 📱 [GitHub Releases](https://github.com/ibrahmsql/CloudVault/releases)
- 🎯 [GitHub Actions](https://github.com/ibrahmsql/CloudVault/actions)

kontrol edebilirsiniz.