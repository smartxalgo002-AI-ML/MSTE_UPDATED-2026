@echo off
echo ==================================================
echo   SETTING UP GPU ENVIRONMENT FOR NEWS TRADER
echo ==================================================
echo.

echo 1. Installing standard dependencies...
pip install -r requirements.txt

echo.
echo 2. Overwriting PyTorch with CUDA 12.4 version...
echo    (This allows GPU acceleration for 10x faster training)
pip uninstall -y torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124

echo.
echo ==================================================
echo   SETUP COMPLETE!
echo ==================================================
echo.
echo To run training (20 mins on GPU):
echo   python train_historic.py --force
echo.
echo To run live pipeline:
echo   python main.py
echo.
pause
