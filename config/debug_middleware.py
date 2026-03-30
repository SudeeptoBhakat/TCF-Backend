import traceback
import sys
import os

class PrintExceptionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        error_msg = traceback.format_exc()
        print("\n\n=============== CRITICAL 500 ERROR CAUGHT BY MIDDLEWARE ===============", file=sys.stderr)
        print(f"Path: {request.path}", file=sys.stderr)
        print(error_msg, file=sys.stderr)
        print("=======================================================================\n\n", file=sys.stderr)
        
        # Write to a file so Antigravity can read it safely
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'admin_crash_traceback.log')
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(error_msg)
        
        return None # Let Django continue its normal 500 handling
