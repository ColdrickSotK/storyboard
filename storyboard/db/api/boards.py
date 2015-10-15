# Copyright (c) 2015 Codethink Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from sqlalchemy.orm import subqueryload
from wsme.exc import ClientSideError

from storyboard.common import exception as exc
from storyboard.db.api import base as api_base
from storyboard.db.api import users as users_api
from storyboard.db import models
from storyboard.openstack.common.gettextutils import _  # noqa


def _board_get(id, session=None):
    if not session:
        session = api_base.get_session()
    query = session.query(models.Board).options(
        subqueryload(models.Board.lanes)).filter_by(id=id)

    return query.first()


def get(id):
    return _board_get(id)


def get_all(title=None, creator_id=None, user_id=None, project_id=None,
            sort_field=None, sort_dir=None, **kwargs):
    if user_id is not None:
        user = users_api.user_get(user_id)
        boards = []
        for board in get_all():
            if any(p in board.permissions for p in user.permissions):
                boards.append(board)
        return boards

    return api_base.entity_get_all(models.Board,
                                   title=title,
                                   creator_id=creator_id,
                                   project_id=project_id,
                                   sort_field=sort_field,
                                   sort_dir=sort_dir,
                                   **kwargs)


def create(values):
    board = api_base.entity_create(models.Board, values)
    return board


def update(id, values):
    return api_base.entity_update(models.Board, id, values)


def add_lane(board_id, lane_dict):
    board = _board_get(board_id)
    if board is None:
        raise exc.NotFound(_("Board %s not found") % board_id)

    # Make sure we're adding the lane to the right board
    lane_dict['board_id'] = board_id

    if lane_dict.get('list_id') is None:
        raise ClientSideError(_("A lane must have a worklist_id."))

    if lane_dict.get('position') is None:
        lane_dict['position'] = len(board.lanes)

    api_base.entity_create(models.BoardWorklist, lane_dict)

    return board


def update_lane(board_id, lane, new_lane):
    # Make sure we aren't messing up the board ID
    new_lane['board_id'] = board_id

    if new_lane.get('list_id') is None:
        raise ClientSideError(_("A lane must have a worklist_id."))

    api_base.entity_update(models.BoardWorklist, lane.id, new_lane)


def get_from_lane(worklist):
    for board in get_all():
        if worklist.id in [lane.list_id for lane in board.lanes]:
            return board


def get_owners(board_id):
    board = _board_get(board_id)
    for permission in board.permissions:
        if permission.codename == 'edit_board':
            return [user.id for user in permission.users]


def get_users(board_id):
    board = _board_get(board_id)
    for permission in board.permissions:
        if permission.codename == 'move_cards':
            return [user.id for user in permission.users]


def get_permissions(board_id, user_id):
    board = _board_get(board_id)
    user = users_api.user_get(user_id)
    if user is not None:
        return [perm.codename for perm in board.permissions
                if perm in user.permissions]
    return []


def create_permission(board_id, permission_dict, session=None):
    board = _board_get(board_id, session=session)
    users = permission_dict.pop('users')
    permission = api_base.entity_create(
        models.Permission, permission_dict, session=session)
    board.permissions.append(permission)
    for user_id in users:
        user = users_api.user_get(user_id, session=session)
        user.permissions.append(permission)
    return permission


def update_permission(board_id, permission_dict):
    board = _board_get(board_id)
    id = None
    for p in board.permissions:
        if p.codename == permission_dict['codename']:
            id = p.id
    users = permission_dict.pop('users')
    permission_dict['users'] = []
    for user_id in users:
        user = users_api.user_get(user_id)
        permission_dict['users'].append(user)

    if id is None:
        raise ClientSideError(_("Permission %s does not exist")
                              % permission_dict['codename'])
    return api_base.entity_update(models.Permission, id, permission_dict)
