from flask import Flask, jsonify, abort, make_response, request
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from database import db
from models import User, Group
from sqlalchemy import or_

# Cria uma instância do banco de dados
def create_app():
    """
    Instantiate Flask

    Implemented as a factory method to avoid a circular import error.
    """
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://localhost/scim"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

app = create_app()

def auth_required(func):
    """Flask decorator to require the presence of a valid Authorization header."""

    @wraps(func)
    def check_auth(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer ") and auth_header.split("Bearer ")[1] == "123456789":
            return func(*args, **kwargs)
        else:
            return make_response(jsonify({"error": "Unauthorized"}), 403)

    return check_auth

@app.route("/scim/v2/Users", methods=["GET"])
@auth_required
def get_users():
    """Get SCIM Users"""
    start_index = request.args.get("startIndex", 1, type=int)
    count = request.args.get("count", 20, type=int)

    filter_value = request.args.get("filter")
    if filter_value and "externalId" in filter_value:
        externalId = filter_value.split(" ")[2].strip('"')
        users = User.query.filter_by(externalId=externalId).all()
    else:
        users = User.query.paginate(page=start_index, per_page=count, error_out=False).items

    serialized_users = [user.serialize() for user in users]

    return make_response(
        jsonify({
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
            "totalResults": len(serialized_users),
            "startIndex": start_index,
            "itemsPerPage": len(serialized_users),
            "Resources": serialized_users,
        }), 200)

@app.route("/scim/v2/Users/<string:user_id>", methods=["GET"])
@auth_required
def get_user(user_id):
    """Get SCIM User"""
    user = User.query.get(user_id)
    if not user:
        return make_response(
            jsonify({
                "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                "detail": "User not found",
                "status": 404,
            }), 404)
    return jsonify(user.serialize())

@app.route("/scim/v2/Users", methods=["POST"])
@auth_required
def create_user():
    """Create SCIM User"""
    data = request.json

    active = data.get("active")
    displayName = data.get("displayName")
    emails = data.get("emails")
    externalId = data.get("externalId")
    groups = data.get("groups")
    locale = data.get("locale")
    name = data.get("name", {})
    givenName = name.get("givenName", None)
    middleName = name.get("middleName", None)
    familyName = name.get("familyName", None)
    password = data.get("password")
    userName = data.get("userName")

    existing_user = User.query.filter_by(userName=userName).first()

    if existing_user:
        return make_response(
            jsonify(
                {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                    "detail": "User already exists in the database.",
                    "status": 409,
                }
            ),
            409,
        )
    else:
        try:
            user = User(
                active=active,
                displayName=displayName,
                emails_primary=emails[0]["primary"] if emails else None,
                emails_value=emails[0]["value"] if emails else None,
                emails_type=emails[0]["type"] if emails else None,
                externalId=externalId,
                locale=locale,
                givenName=givenName,
                middleName=middleName,
                familyName=familyName,
                password=password,
                userName=userName,
            )
            db.session.add(user)

            if groups:
                for group in groups:
                    existing_group = Group.query.get(group["value"])

                    if existing_group:
                        existing_group.users.append(user)
                    else:
                        new_group = Group(displayName=group["displayName"])
                        db.session.add(new_group)
                        new_group.users.append(user)

            db.session.commit()
            return make_response(jsonify(user.serialize()), 201)
        except Exception as e:
            return make_response(jsonify({"error": str(e)}), 500)  # Retorna erro 500 em caso de exceção

@app.route("/scim/v2/Users/<string:user_id>", methods=["PUT"])
@auth_required
def update_user(user_id):
    """Update SCIM User"""
    user = User.query.get(user_id)

    if not user:
        return make_response(
            jsonify(
                {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                    "detail": "User not found",
                    "status": 404,
                }
            ),
            404,
        )
    else:
        data = request.json
        user.active = data.get("active", user.active)
        user.displayName = data.get("displayName", user.displayName)
        user.emails_primary = data["emails"][0]["primary"] if data.get("emails") else user.emails_primary
        user.emails_value = data["emails"][0]["value"] if data.get("emails") else user.emails_value
        user.emails_type = data["emails"][0]["type"] if data.get("emails") else user.emails_type
        user.externalId = data.get("externalId", user.externalId)
        user.locale = data.get("locale", user.locale)
        name = data.get("name", {})
        user.givenName = name.get("givenName", None)
        user.middleName = name.get("middleName", None)
        user.familyName = name.get("familyName", None)
        user.password = data.get("password", user.password)
        user.userName = data.get("userName", user.userName)

        # Atualiza os grupos
        if "groups" in data:
            user.groups = []
            for group in data["groups"]:
                existing_group = Group.query.get(group["value"])

                if existing_group:
                    existing_group.users.append(user)
                else:
                    new_group = Group(displayName=group["displayName"])
                    db.session.add(new_group)
                    new_group.users.append(user)

        db.session.commit()
        return make_response(jsonify(user.serialize()), 200)

@app.route("/scim/v2/Users/<string:user_id>", methods=["PATCH"])
@auth_required
def deactivate_user(user_id):
    """Deactivate SCIM User"""
    data = request.json
    is_user_active = data["Operations"][0]["value"].get("active")

    user = User.query.get(user_id)
    if not user:
        return make_response(
            jsonify(
                {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                    "detail": "User not found",
                    "status": 404,
                }
            ),
            404,
        )
    
    user.active = is_user_active

    db.session.commit()
    return make_response("", 204)

@app.route("/scim/v2/Users/<string:user_id>", methods=["DELETE"])
@auth_required
def delete_user(user_id):
    """Delete SCIM User"""
    user = User.query.get(user_id)
    if not user:
        return make_response(
            jsonify(
                {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                    "detail": "User not found",
                    "status": 404,
                }
            ),
            404,
        )

    db.session.delete(user)
    db.session.commit()
    return make_response("", 204)


@app.route("/scim/v2/Groups", methods=["GET"])
@auth_required
def get_groups():
    """Get SCIM Groups"""
    filter_str = request.args.get("filter")
    excluded_attributes = request.args.get("excludedAttributes", "")

    # Converte os atributos excluídos em uma lista
    excluded_attributes_list = excluded_attributes.split(",") if excluded_attributes else []

    query = Group.query

    if filter_str:
        # Adiciona a lógica para filtrar grupos com base no parâmetro 'filter'
        filter_str = filter_str.strip()  # Remove espaços em branco extras

        # Extraindo o nome do atributo e valor do filtro
        if "eq" in filter_str:
            attribute, value = filter_str.split(" eq ")
            attribute = attribute.strip()
            value = value.strip('"').strip()

            if attribute == "externalId":
                query = query.filter(Group.externalId == value)
            else:
                return make_response(
                    jsonify(
                        {
                            "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                            "detail": "Unsupported filter attribute",
                            "status": 400,
                        }
                    ),
                    400,
                )
        else:
            return make_response(
                jsonify(
                    {
                        "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                        "detail": "Invalid filter syntax",
                        "status": 400,
                    }
                ),
                400,
            )

    groups = query.all()

    # Se não houver grupos, retorne uma resposta com totalResults e Resources vazios
    if not groups:
        return make_response(
            jsonify(
                {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
                    "totalResults": 0,
                    "Resources": [],
                    "startIndex": 1,
                    "itemsPerPage": 0,
                }
            ),
            200,
        )

    include_members = "members" not in excluded_attributes_list

    return jsonify({
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(groups),
        "Resources": [e.serialize(include_members) for e in groups],
        "startIndex": 1,
        "itemsPerPage": 20,
    })

    
@app.route("/scim/v2/Groups/<string:group_id>", methods=["GET"])
@auth_required
def get_group(group_id):
    """Get SCIM Group"""
    group = Group.query.get(group_id)
    if not group:
        return make_response(
            jsonify(
                {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                    "detail": "Group not found",
                    "status": 404,
                }
            ),
            404,
        )

    excluded_attributes = request.args.get("excludedAttributes", "")
    excluded_attributes_list = excluded_attributes.split(",") if excluded_attributes else []

    include_members = "members" not in excluded_attributes_list

    return jsonify(group.serialize(include_members))


@app.route("/scim/v2/Groups", methods=["POST"])
@auth_required
def create_group():
    """Create SCIM Group"""
    data = request.json
    displayName = data["displayName"]
    externalId = data["externalId"]
    members = data.get("members", [])

    try:
        group = Group(displayName=displayName, externalId=externalId)
        db.session.add(group)

        for member in members:
            existing_user = User.query.get(member["value"])
            if existing_user:
                group.users.append(existing_user)

        db.session.commit()
        return make_response(jsonify(group.serialize()), 201)
    except Exception as e:
        return make_response(jsonify({"error": str(e)}), 500)  # Retorna erro 500 em caso de exceção

@app.route("/scim/v2/Groups/<string:group_id>", methods=["PATCH", "PUT"])
@auth_required
def update_group(group_id):
    """
    Update SCIM Group

    Accounts for the different requests sent by Okta depending
    on if the group was created via template or app wizard integration.
    """
    data = request.json
    members = data.get("members", [])
    
    group = Group.query.get(group_id)
    if not group:
        return make_response(
            jsonify(
                {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                    "detail": "Group not found",
                    "status": 404,
                }
            ),
            404,
        )

    if data.get("Operations"):
        for operation in data["Operations"]:
            op = operation["op"]
            value = operation.get("value", {})

            if op == "replace":
                group.users = []  # Limpa os usuários atuais
                for member in value.get("members", []):
                    existing_user = User.query.get(member["value"])
                    if existing_user:
                        group.users.append(existing_user)
                db.session.commit()
                return make_response("", 204)

    else:
        for member in members:
            existing_user = User.query.get(member["value"])
            if existing_user:
                group.users.append(existing_user)

    db.session.commit()
    return make_response(jsonify(group.serialize()), 200)

@app.route("/scim/v2/Groups/<string:group_id>", methods=["DELETE"])
@auth_required
def delete_group(group_id):
    """Delete SCIM Group"""
    group = Group.query.get(group_id)
    if not group:
        return make_response(
            jsonify(
                {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
                    "detail": "Group not found",
                    "status": 404,
                }
            ),
            404,
        )

    db.session.delete(group)
    db.session.commit()
    return make_response("", 204)

if __name__ == "__main__":
    app.run(debug=True)
