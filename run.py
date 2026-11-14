from multiprocessing import freeze_support

from app.main import main

if __name__ == "__main__":
    freeze_support()
    main()
