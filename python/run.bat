@echo off
chcp 65001
cd /d "%~dp0"
echo 社宅爬蟲啟動中...
python social_housing_crawler.py
pause