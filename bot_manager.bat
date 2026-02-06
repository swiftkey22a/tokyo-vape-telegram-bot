@echo off
chcp 65001 > nul
title Управление ботом Tokyo Vape
echo ========================================
echo    УПРАВЛЕНИЕ БОТОМ TOKYO VAPE
echo ========================================
echo.
echo 1. Запустить бот
echo 2. Остановить бот
echo 3. Просмотреть логи
echo 4. Перезапустить бот
echo.
set /p choice="Выберите действие (1-4): "

if "%choice%"=="1" (
    echo Запуск бота...
    start "Tokyo Vape Bot" "D:\sales tokyo vape\start_bot.bat"
) else if "%choice%"=="2" (
    echo Остановка бота...
    taskkill /F /IM python.exe /T
    timeout /t 2 /nobreak > nul
) else if "%choice%"=="3" (
    echo Открываю логи...
    notepad "D:\sales tokyo vape\bot_errors.log"
    pause
) else if "%choice%"=="4" (
    echo Перезапуск бота...
    taskkill /F /IM python.exe /T
    timeout /t 2 /nobreak > nul
    start "Tokyo Vape Bot" "D:\sales tokyo vape\start_bot.bat"
)