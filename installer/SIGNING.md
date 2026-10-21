# Firma de código / SmartScreen

Windows muestra **“Windows protegió tu PC”** cuando el `.exe` **no está firmado** con un certificado de confianza (o es muy nuevo y aún no tiene reputación).

## Qué NO sirve

- Certificado **autofirmado** → SmartScreen sigue avisando (o empeora).
- Solo cambiar el nombre / icono → no quita el aviso.

## Qué hace falta (de pago)

1. Certificado **Code Signing** OV o EV (DigiCert, Sectigo, SSL.com, GlobalSign…).
   - Precio orientativo: ~150–400 €/año (OV) · EV suele ser más caro.
2. En Windows, con el certificado instalado o un `.pfx`:

```bat
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f tu_cert.pfx /p TU_PASSWORD dist\Valkyrium_OneFile\ValkyriumBossTracker.exe
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 /f tu_cert.pfx /p TU_PASSWORD dist\ValkyriumSetup_v0.2.2.exe
```

3. Publicar el instalador/EXE firmados en GitHub Releases.

Con el tiempo, descargas reales también mejoran la reputación SmartScreen (aunque la firma es lo fiable).

## Mientras tanto (usuarios)

En el aviso de SmartScreen: **Más información** → **Ejecutar de todas formas**.
Es normal en software indie sin certificado de pago.
