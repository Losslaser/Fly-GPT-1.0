FlyGPT - Windows build and installer notes
==========================================

WHAT THIS BUILDS
- A Windows app folder containing FlyGPT.exe and bundled Python runtime.
- An Inno Setup installer that installs that folder per user.
- An optional setup step that installs official Ollama (if missing) and pulls qwen2.5:0.5b.
- The connectome CSV and annotation TSV are copied into the app folder if present.

REQUIREMENTS ON THE DEVELOPER PC
- Windows 10/11
- Python 3.11+ with the Python Launcher (py)
- Inno Setup 6 to compile FlyGPT.iss
- The two data files in this same project folder:
  connections_princeton.csv
  Supplemental_file1_neuron_annotations.tsv

BUILD THE EXE
1. Put main.py, both data files, build_windows.bat, SetupOllama.ps1,
   FlyGPT.iss and this README in one folder.
2. Double-click build_windows.bat.
3. Test dist\FlyGPT\FlyGPT.exe before making an installer.
4. Install Inno Setup 6 and open FlyGPT.iss in Inno Setup Compiler.
5. Click Compile. The installer will be written to installer_output.

IMPORTANT
- Build the Windows EXE on Windows; a Linux-built PyInstaller executable is not a Windows EXE.
- The large connectome and annotation files are not included in this starter package,
  because they were not present in the files available for this build. Add your own
  dataset files before creating a full installer.
- Ollama and the model are downloaded separately during setup, so the installer is
  smaller and can get a newer Ollama release. The first setup requires internet.
- The app saves fly_memory.json to %LOCALAPPDATA%\FlyGPT when running as an EXE.
- The app uses local Ollama at http://localhost:11434. Ollama must be running.
- The current main.py loads the connectome into memory; very large CSV files can use
  substantial RAM and make startup slower.


PERSONALITY + DATA PATH UPDATE
- This build uses a stronger fly-like role prompt: it should react to cues and not behave like a customer-service assistant. Small local models can still occasionally ignore instructions.
- The app now searches for the connectome CSV and annotation TSV beside FlyGPT.exe and in a data\ subfolder.
- Put both files in the same folder as main.py before building. The build script copies them beside FlyGPT.exe when present.
