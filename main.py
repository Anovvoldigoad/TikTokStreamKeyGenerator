"""Android deployment entrypoint; preserve the existing desktop application."""
import os

# Never load local development signing algorithms into a release APK.
os.environ["TIKTOK_SIGNER_MODE"] = "api"

from TiktokStreamKeyGenerator import main


if __name__ == "__main__":
    main()
