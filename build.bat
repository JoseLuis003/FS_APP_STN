@echo off
REM Compila FS_APP_STN a un unico .exe. Ejecutar en Windows con Python instalado.

python -m venv .venv
call .venv\Scripts\activate.bat
pip install -r requirements.txt
pip install pyinstaller
pyinstaller build.spec

echo.
echo Listo. El ejecutable queda en dist\FS_APP_STN.exe
echo Copia junto a el la carpeta "config" (apps.json y settings.json) si no se genero automaticamente,
echo para que los tecnicos puedan editar el catalogo sin recompilar.
pause
