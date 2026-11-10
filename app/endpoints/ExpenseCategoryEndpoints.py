from flask import Blueprint
from endpoints.middlewares.AuthMiddleware import cryptography_required, signature_required, cipher_and_sign_response
from utils.ResponseMaker import make_response
from utils.Constants import Messages, ExpenseCategoryMessages
from repositories.ExpenseCategoryRepository import ExpenseCategoryRepository
from models.ExpenseCategory import ExpenseCategory
from exceptions.Http import HttpException
from validators.FieldValidator import is_empty

expensecategory_bp = Blueprint('expensecategory', __name__)

@expensecategory_bp.route('/api/v1/ExpenseCategory/id', methods=['POST'])
@cryptography_required
@cipher_and_sign_response
def get_by_id(user_id, session, user, decrypted_data):
    try:
        data = decrypted_data
        is_empty(data, ["id"])

        cat_id = data.get('id')
        
        category = ExpenseCategoryRepository.get_by_id(catId, session)
        if not category:
            return make_response(None, False, ExpenseCategoryMessages.NOT_FOUND), 200

        response = make_response(category, True, ExpenseCategoryMessages.FETCHED), 200
        session.remove()

        return response
    
    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500
    

@expensecategory_bp.route('/api/v1/ExpenseCategory/all', methods=['GET'])
@signature_required
@cipher_and_sign_response
def get_all(user_id, session, user):
    try:  
        categories = ExpenseCategoryRepository.get_all(session)
        
        response = make_response(categories, True, ExpenseCategoryMessages.FETCHED_PLURAL), 200
        session.remove()

        return response

    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500
    

@expensecategory_bp.route('/api/v1/ExpenseCategory/', methods=['POST'])
@cryptography_required
@cipher_and_sign_response
def create_expense_category(user_id, session, user, decrypted_data):
    try:
        data = decrypted_data
        is_empty(data, ["name"])
        
        cat_name = data.get("name")
        
        new_category = ExpenseCategory(name=cat_name)
        new_category.save(session)


        response = make_response(new_category, True, ExpenseCategoryMessages.CREATED), 200
        session.remove()

        return response

    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500
    
@expensecategory_bp.route('/api/v1/ExpenseCategory/delete', methods=['POST'])
@cryptography_required
def delete(user_id, session, user, decrypted_data):
    try:
        data = decrypted_data
        is_empty(data, ["id"])
        
        cat_id = data.get('id')

        ExpenseCategoryRepository.delete_by_id(catId, session)
        session.remove()
        
        return make_response(None, True, ExpenseCategoryMessages.DELETED), 200

    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500
    
@expensecategory_bp.route('/api/v1/ExpenseCategory/', methods=['PATCH'])
@cryptography_required
@cipher_and_sign_response
def edit_name(user_id, session, user, decrypted_data):
    try:
        data = decrypted_data
        is_empty(data, ["id", "name"])

        cat = ExpenseCategoryRepository.get_by_id(data.get('id'), session)
        
        cat.setName(data.get('name'))
        cat.save(session)

        return make_response(cat, True, ExpenseCategoryMessages.MODIFIED), 200

    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500