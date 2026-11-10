from datetime import datetime
from flask import Blueprint, jsonify
from models.Expense import Expense
from repositories.ExpenseRepository import ExpenseRepository
from repositories.SeasonRepository import SeasonRepository
from endpoints.middlewares.AuthMiddleware import cryptography_required, signature_required, cipher_and_sign_response
from utils.ResponseMaker import make_response
from utils.Constants import Messages, ExpenseMessages
from exceptions.Http import HttpException
from validators.FieldValidator import is_empty

expense_bp = Blueprint('expense', __name__)

@expense_bp.route('/api/v1/Expense/id', methods=['POST'])
@cryptography_required
@cipher_and_sign_response
def get_by_id(user_id, session, user, decrypted_data):
    try:
        data = decrypted_data
        is_empty(data, ["id"])
        
        expense_id = data.get('id')

        expense = ExpenseRepository.get_by_id(expense_id, session)
        if not expense:
            return make_response(None, False, ExpenseMessages.NOT_FOUND), 200
        
        response = make_response(expense, True, ExpenseMessages.FETCHED), 200
        session.remove()

        return response
    
    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500
    

@expense_bp.route('/api/v1/Expense/category/', methods=['POST'])
@cryptography_required
@cipher_and_sign_response
def get_by_category(user_id, session, user, decrypted_data):
    try:
        data = decrypted_data
        is_empty(data, ["catId"])
        
        cat_id = data.get('catId')
        if not cat_id:
            return jsonify({'error': 'Category not provided'}), 403
        expenses = ExpenseRepository.get_by_category(cat_id, session)  
        
        response = make_response(expenses, True, ExpenseMessages.FETCHED_PLURAL), 200
        session.remove()

        return response
    
    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500

@expense_bp.route('/api/v1/Expense/season/', methods=['POST'])
@cryptography_required
@cipher_and_sign_response
def get_by_season(user_id, session, user, decrypted_data):
    try:
        is_empty(decrypted_data, ["seasonId"])
        expenses = ExpenseRepository.get_by_season(decrypted_data.get('seasonId'), session)
        response = make_response(expenses, True, ExpenseMessages.FETCHED_PLURAL), 200
        session.remove()
        return response
    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500

@expense_bp.route('/api/v1/Expense/', methods=['POST'])
@cryptography_required
@cipher_and_sign_response
def create_expense(user_id, session, user, decrypted_data):
    try:
        data = decrypted_data
        is_empty(data, ["price", "expenseDate", "category"])

        price = data.get('price')
        expense_date = data.get('expenseDate')
        cat_id = data.get('category')
        description = data.get('description')

        parsed_date = datetime.strptime(expense_date, "%Y-%m-%d")
        season = SeasonRepository.get_or_create(parsed_date.year, parsed_date.month, session)

        new_expense = Expense(
            price=price,
            category=cat_id,
            expenseDate=expense_date,
            description=description,
            seasonId=season.id
        )

        new_expense.save(session)
        response = make_response(new_expense, True, ExpenseMessages.CREATED), 200
        session.remove()
        return response

    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500
    
@expense_bp.route('/api/v1/Expense/all/', methods=['DELETE'])
@signature_required
def delete_all(user_id, session, user):
    try:
        ExpenseRepository.delete_all(session)
        response = make_response(None, True, ExpenseMessages.DELETED_PLURAL), 200
        session.remove()
        return response
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500
    
@expense_bp.route('/api/v1/Expense/delete', methods=['POST'])
@cryptography_required
def delete_by_id(user_id, session, user, decrypted_data):
    try:
        data = decrypted_data
        is_empty(data, ["id"])

        expense_id = data.get("id")
        
        ExpenseRepository.delete_by_id(expense_id, session)
        
        response = make_response(None, True, ExpenseMessages.DELETED), 200
        session.remove()

        return response
    
    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500

@expense_bp.route('/api/v1/Expense/', methods=['PATCH'])
@cryptography_required
@cipher_and_sign_response
def edit(user_id, session, user, decrypted_data):
    try:
        data = decrypted_data
        is_empty(data, ["id"])

        expense_id = data.get("id")
        exp = ExpenseRepository.get_by_id(expense_id, session)
        if not exp:
            return make_response(None, False, ExpenseMessages.NOT_FOUND), 200    

        exp.edit(**data)

        if data.get('expenseDate'):
            parsed_date = datetime.strptime(data.get('expenseDate'), "%Y-%m-%d")
            season = SeasonRepository.get_or_create(parsed_date.year, parsed_date.month, session)
            exp.seasonId = season.id

        exp.save(session)

        response = make_response(exp, True, ExpenseMessages.MODIFIED), 200
        session.remove()
        return response

    except HttpException as e:
        return make_response(None, False, e.message, e.inner_exception), e.status_code
    except Exception as e:
        return make_response(None, False, Messages.INTERNAL_ERROR, e), 500
