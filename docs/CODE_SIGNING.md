# Code signing policy

*[Türkçe özet aşağıda](#türkçe-özet)*

> **Status:** Truck TMS applied to the [SignPath Foundation](https://signpath.org/) open-source program in November 2026.
> The application **has not been approved yet**, because the project does not have enough downloads and public visibility
> so far. We plan to reapply once it has more users. Until then, `TruckTMS.exe` releases are **not code-signed**.
> Once a certificate is issued, Windows releases will be signed as described below and this notice will be replaced by:
> *Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).*

## What is signed

- **`TruckTMS.exe`**, the Windows program attached to each [release](https://github.com/ArslanEren-Dev/truck-tms/releases).
- It is built only by the [release workflow](../.github/workflows/release.yml) on GitHub Actions, directly from the source code
  in this repository ([ArslanEren-Dev/truck-tms](https://github.com/ArslanEren-Dev/truck-tms)). It is never built on a personal computer.
- The workflow runs the full test suite and the exe's own `--self-test` before the exe is published.
- Libraries bundled inside the exe are not re-signed. They already carry their vendors' signatures:
  The Qt Company (Qt/PySide6), Python Software Foundation (Python) and Microsoft (Visual C++ runtime).

## Team roles

| Role | Members |
|---|---|
| Committers and reviewers | [ArslanEren-Dev](https://github.com/ArslanEren-Dev) |
| Approvers | [ArslanEren-Dev](https://github.com/ArslanEren-Dev) |

Truck TMS currently has a single maintainer, who owns the repository and approves every signing request.
All team members use multi-factor authentication for GitHub and SignPath.
External contributions are accepted only through reviewed pull requests.

## Privacy policy

Apart from the optional update check described below, this program does not transfer any information to other networked
systems unless the user specifically requests it.

- All data (trucks, drivers, loads, statements and settings) is stored in a local file on the user's computer.
- The program has no accounts, telemetry, analytics or advertising.
- **Update check:** once a day, the program reads the latest public release of this repository from the GitHub API
  (`https://api.github.com/repos/ArslanEren-Dev/truck-tms/releases/latest`) to let the user know when a new version
  is available. The request contains no information about the user or their records; GitHub receives only what every
  web request carries, such as the IP address. The check can be turned off under **Settings → Updates**, and
  **Help → Check for updates** runs it on demand.
- Any other network access happens only when the user chooses **Help → Project Website**, **Source Code on GitHub**
  or **Report a Problem**, which opens the page in the user's own web browser.

## Maintainer setup (one time)

1. Apply at <https://signpath.org/> for the open-source program with this repository.
2. In SignPath, create the project **`truck-tms`** with this artifact configuration
   (the workflow uploads `TruckTMS.exe` as a ZIP artifact):

   ```xml
   <?xml version="1.0" encoding="utf-8"?>
   <artifact-configuration xmlns="http://signpath.io/artifact-configuration/v1">
     <zip-file>
       <pe-file path="TruckTMS.exe">
         <authenticode-sign />
       </pe-file>
     </zip-file>
   </artifact-configuration>
   ```

3. Create the signing policy **`release-signing`** that uses the SignPath Foundation certificate, with manual approval by an approver.
4. In GitHub: **Settings → Secrets and variables → Actions**
   - add the **variable** `SIGNPATH_ORGANIZATION_ID` with your SignPath organization ID;
   - add the **secret** `SIGNPATH_API_TOKEN` with a SignPath API token.
5. Publish the next release. The workflow then submits the exe to SignPath, waits for the approval, checks that the signature
   is valid, runs the self-test on the signed exe and attaches it to the release.

---

## Türkçe özet

- **Durum:** [SignPath Foundation](https://signpath.org/) açık kaynak programına Kasım 2026'da başvuruldu. Proje henüz yeterli indirme ve
  bilinirliğe ulaşmadığı için başvuru **şimdilik onaylanmadı**; kullanıcı sayısı arttığında yeniden başvurulacak. O zamana kadar
  `TruckTMS.exe` **imzasızdır**.
- **İmzalanan dosya:** Yalnızca `TruckTMS.exe`. Bu dosya kişisel bir bilgisayarda değil, her zaman bu repodaki koddan
  GitHub Actions tarafından derlenir. İçindeki Qt, Python ve Microsoft kütüphaneleri zaten kendi üreticileri tarafından imzalıdır.
- **Ekip:** Tek geliştirici ve onaylayıcı [ArslanEren-Dev](https://github.com/ArslanEren-Dev). GitHub ve SignPath hesaplarında iki aşamalı doğrulama kullanılır.
- **Gizlilik:** Güncelleme kontrolü dışında program, kullanıcı özellikle istemedikçe hiçbir bilgiyi
  başka bir ağ sistemine göndermez. Bütün veriler kullanıcının bilgisayarındaki bir dosyada durur. Hesap, telemetri ya da
  reklam yoktur. Program günde bir kez GitHub'daki herkese açık sürüm bilgisine bakarak yeni sürüm olup olmadığını kontrol
  eder; bu istekte kullanıcıya veya kayıtlarına ait hiçbir bilgi bulunmaz. Kontrol **Ayarlar → Güncellemeler** bölümünden
  kapatılabilir. Bunun dışında internet yalnızca kullanıcı **Yardım** menüsünden bir bağlantı seçtiğinde, kendi tarayıcısında
  açılır.
- **Kurulum:** Yukarıdaki "Maintainer setup" adımları uygulandığında imzalama, release akışında kendiliğinden devreye girer.
