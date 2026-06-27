# Likha Homes Revenue Dashboard — Deploy to GitHub Pages

Repo local listo en: `C:\Users\ASUS\likha-dashboard\`  
Commit inicial: `3c4dbd9 feat: launch Likha Homes Revenue Dashboard 2026`

---

## Pasos para publicar (5 minutos)

### 1. Crear repo en GitHub

Ir a: https://github.com/new

- **Repository name:** `likha-dashboard`
- **Visibility:** Public (requerido para GitHub Pages gratis)
- **NO** marcar "Add README", "Add .gitignore", ni nada más
- Clic en **"Create repository"**

### 2. Conectar repo local y hacer push

Abrir PowerShell en `C:\Users\ASUS\likha-dashboard\` y ejecutar:

```powershell
cd C:\Users\ASUS\likha-dashboard

# Reemplaza TU_USERNAME con tu usuario de GitHub
git remote add origin https://github.com/TU_USERNAME/likha-dashboard.git

git push -u origin main
```

GitHub pedirá credenciales la primera vez — usa tu usuario y un Personal Access Token (no la contraseña).

### 3. Activar GitHub Pages

En el repo recién creado en GitHub:

1. Ir a **Settings** → **Pages** (columna izquierda)
2. En "Branch": seleccionar **main** → carpeta **/ (root)**
3. Clic en **Save**

GitHub tarda ~2 minutos en publicar.

### 4. URL del dashboard

```
https://TU_USERNAME.github.io/likha-dashboard
```

---

## Actualizar datos en el futuro

Los datos están hardcodeados en `index.html` (líneas ~350-420, array `PROPERTIES`).  
Para actualizar: editar el array y hacer `git push`.

```powershell
cd C:\Users\ASUS\likha-dashboard
git add index.html
git commit -m "feat: update revenue data YYYY-MM-DD"
git push
```

GitHub Pages se actualiza automáticamente en ~1 minuto.
