@echo off
rem Chay check listing moi + QA cho ngay UK vua ket thuc (chay buoi sang gio VN), xong tu mo file Excel. Bam dup chuot de chay.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
python check_new_listings.py --yesterday
if errorlevel 1 goto end
python qa_listings.py --yesterday --refresh --open
:end
if "%1"=="" pause
