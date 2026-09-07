# Source archive

The full U DINK STORE source history is stored as Base64-split ZIP parts because the handoff was transferred through a text-file API.

To restore everything locally:

```bash
python tools/restore_source.py
```

This creates:
- `U_DINK_STORE_ALL_SOURCE.zip`
- `restored-source/`

The restored package includes the historical V1–V4 prototype sources and documentation.
