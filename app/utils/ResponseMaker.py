from flask import jsonify
from utils.Logger import AppLogger
from utils.Constants import Messages
import traceback

class Response:
    def __init__(self, data=None, success=True, message=""):
        self.success = success
        self.message = message
        self.data = data

    def to_dict(self):
        if isinstance(self.data, list):
            data_value = [
                item.to_json_dict() if hasattr(item, "to_json_dict") else item
                for item in self.data
            ]
        else:
            data_value = self.data.to_json_dict() if self.data is not None and hasattr(self.data, "to_json_dict") else self.data
        return {
            "success": self.success,
            "message": self.message,
            "data": data_value
        }

def make_response(data=None, success=True, message="", exception=None, debug=False):
    try:
        log_message = message
        if success:
            AppLogger.info(message)
        else:
            if exception is not None:

                # Driver exceptions can embed SQL bind parameters (including secrets).
                AppLogger.error("%s [%s]", log_message, type(exception).__name__)
            else:
                AppLogger.error(log_message)
                
        return jsonify(Response(data if data is not None else None, success, message).to_dict())
    
    except Exception as e:
        AppLogger.error(str(e), stack_info=True, exc_info=True)
        return jsonify({
            "success": False,
            "message": Messages.INTERNAL_ERROR,
            "data": None
        }), 500
