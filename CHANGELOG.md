# Changelog — Valkyrium Boss Tracker (by Pinalo)

## v0.2.6

- Al cerrar Valkyrium también se cierra el DPS meter (A2Tools)

## v0.2.5

- El DPS meter (A2Tools) ya **no aparece en la barra de tareas**; solo se ve el overlay del medidor

## v0.2.4

- Quita la tapa fea del engranaje de Ajustes del DPS meter (se deja el botón nativo de A2Tools)

## v0.2.3

- Catálogo: `a2tools_field_id` en todos los field bosses + 24 bosses asmodianos Altgard (HP% correcto, sin mezclar Elyos/Asmo)
- Abismo: Argo con field `2001`; Kaira solo horario (sin HP en feed)
- Al abrir Valkyrium: auto-update silencioso + lanza/ajusta A2Tools (meter on, Event Timers off)
- Título del meter → **Valkyrium DPS Meter**

## v0.2.2

- Lista desplegable de servidores EU / NA East / NA West (Kaisinel, Lumiel, …) con serverId correcto
- Instalador `ValkyriumSetup` (icono escritorio + desinstalar) vía Inno Setup
- Notas de firma/SmartScreen en `installer/SIGNING.md` (requiere certificado de pago)

## v0.2.1

- Auto-update del **EXE onefile**: descarga el `.exe` nuevo, lo sustituye y reinicia
- Manifiesto con `exe_url` + `url` (zip carpeta)
- Toast al detectar versión nueva

## v0.2.0

### Overlay y UX
- Menú de bandeja con estado live (● conectado / ○ desconectado), servidor, región y facción
- Toast propio al copiar `#TP` (sin depender solo de notificaciones de Windows)
- Posición del overlay memorizada al arrastrar
- Escala (Ctrl+rueda) y opacidad (rueda) desde overlay y menú
- Contador siempre visible de la siguiente ventana de **Velador Kaira**
- Favoritos (★ clic derecho): siempre visibles en el strip aunque no estén en ventana ≤5 min
- Historial de kills del día en el menú de bandeja
- Diálogo **About** con logo P + versión
- Wizard de primera vez (servidor → facción → overlay)

### Live / datos
- HP live vía WSS A2Tools embebido
- Anillo HP animado; Abyss con anillo púrpura/verde
- Kaira por horario (no se muestra como viva fuera de ventana)
- Argo Spirit King en catálogo para % de abismo

### Empaque
- Portable EXE + `Iniciar_Portable.bat`
- Zip de distribución: `ValkyriumBossTracker_v0.2.0.zip`
