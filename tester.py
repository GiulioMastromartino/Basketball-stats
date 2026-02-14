import unittest
import sys
import os
from dotenv import load_dotenv

def run_tests():
    """Run all tests in the tests directory."""
    # Load environment variables from .env file
    load_dotenv()
    
    # Add the project root to the python path
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    loader = unittest.TestLoader()
    start_dir = 'tests'
    suite = loader.discover(start_dir)
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    if not result.wasSuccessful():
        sys.exit(1)

if __name__ == '__main__':
    run_tests()
