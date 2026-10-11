# Semi-SaaS Admin Commands

Fondasi Semi-SaaS awal sudah tersedia di Telegram bot.

## User Commands

```text
/register
/myaccount
/license
/onboarding
```

User publik bisa memakai command ini dari Telegram. Mereka tidak bisa melihat atau mengontrol akun trading admin.

## Admin Commands

```text
/admin_users
/admin_pending
/admin_approve CHAT_ID [days]
/admin_revoke CHAT_ID [reason]
/admin_extend CHAT_ID days
```

Contoh:

```text
/admin_approve 123456789 7
/admin_extend 123456789 30
/admin_revoke 123456789 unpaid
```

## Access Control

Admin ditentukan dari `telegram.admin_chat_ids` di `config.json`.

Command trading seperti `/positions`, `/orders`, `/pause`, `/resume`, `/report`, `/weekly`, `/monthly`, dan `/alltime` saat ini hanya untuk admin.

Ini disengaja agar calon client tidak bisa melihat data akun owner/admin sebelum worker pribadi per user tersedia.

## Registry File

User registry disimpan di:

```text
C:\Users\YOUR_WINDOWS_USER\.openclaw\workspace\user_registry_v1.json
```

Path bisa diubah lewat:

```json
"paths": {
  "user_registry_path": "..."
}
```

## Status Implementasi

Selesai:

- Registrasi user.
- Status akun.
- Metadata license/trial.
- Admin approve/revoke/extend.
- Guard command trading untuk admin.

Belum:

- Worker trading per user.
- Config/journal per user.
- Secure API vault.
- Auto subscription/payment.
