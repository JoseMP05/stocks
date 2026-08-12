# Comando utiles

```bash
# 1. ¿Quién tiene el puerto?
netstat -ano -p tcp | findstr :8420
#    → la última columna es el PID

# 2. ¿Qué proceso es ese PID?
Get-Process -Id <PID>

# 3. Bajarlo
Stop-Process -Id <PID> -Force
```
