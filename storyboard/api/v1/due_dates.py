# Copyright (c) 2016 Codethink Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from datetime import datetime

from oslo_config import cfg
from pecan import abort
from pecan import request
from pecan import response
from pecan import rest
from pecan.secure import secure
from wsme import types as wtypes
import wsmeext.pecan as wsme_pecan

from storyboard.api.auth import authorization_checks as checks
from storyboard.api.v1 import wmodels
from storyboard.common import decorators
from storyboard.common import exception as exc
from storyboard.db.api import due_dates as due_dates_api
from storyboard.openstack.common.gettextutils import _  # noqa


CONF = cfg.CONF


def visible(due_date, user=None):
    if not due_date:
        return False
    if user and due_date.private:
        permissions = due_dates_api.get_permissions(due_date, user)
        return any(name in permissions for name in ['edit_date', 'view_date'])
    return not due_date.private


def editable(due_date, user=None):
    if not due_date:
        return False
    if not user:
        return False
    return 'edit_date' in due_dates_api.get_permissions(due_date, user)


class PermissionsController(rest.RestController):
    """Manages operations on due date permissions."""

    @decorators.db_exceptions
    @secure(checks.guest)
    @wsme_pecan.wsexpose([wtypes.text], int)
    def get(self, due_date_id):
        """Get due date permissions for the current user.

        :param due_date_id: The ID of the due date.

        """
        due_date = due_dates_api.get(due_date_id)
        return due_dates_api.get_permissions(due_date,
                                             request.current_user_id)

    @decorators.db_exceptions
    @secure(checks.authenticated)
    @wsme_pecan.wsexpose(wtypes.text, int,
                         body=wtypes.DictType(wtypes.text, wtypes.text))
    def post(self, due_date_id, permission):
        """Add a new permission to the due date.

        :param due_date_id: The ID of the due date.
        :param permission: The dict used to create the permission.

        """
        return due_dates_api.create_permission(due_date_id, permission)

    @decorators.db_exceptions
    @secure(checks.authenticated)
    @wsme_pecan.wsexpose(wtypes.text, int,
                         body=wtypes.DictType(wtypes.text, wtypes.text))
    def put(self, due_date_id, permission):
        """Update a permission of the due date.

        :param due_date_id: The ID of the due date.
        :param permission: The new contents of the permission.

        """
        return due_dates_api.update_permission(
            due_date_id, permission).codename


class DueDatesController(rest.RestController):
    """Manages operations on due dates."""

    @decorators.db_exceptions
    @secure(checks.guest)
    @wsme_pecan.wsexpose(wmodels.DueDate, int)
    def get_one(self, id):
        """Retrieve details about one due date.

        :param id: The ID of the due date.

        """
        due_date = due_dates_api.get(id)

        if visible(due_date, request.current_user_id):
            due_date_model = wmodels.DueDate.from_db_model(due_date)
            due_date_model.resolve_items(due_date)
            due_date_model.resolve_permissions(due_date)
            return due_date_model
        else:
            return exc.NotFound(_("Due date %s not found") % id)

    @decorators.db_exceptions
    @secure(checks.guest)
    @wsme_pecan.wsexpose([wmodels.DueDate], wtypes.text, datetime,
                         wtypes.text, wtypes.text)
    def get_all(self, name=None, date=None, sort_field='id', sort_dir='asc'):
        """Retrieve details about all the due dates.

        :param name: The name of the due date.
        :param date: The date of the due date.
        :param sort_field: The name of the field to sort on.
        :param sort_dir: Sort direction for results (asc, desc).

        """
        due_dates = due_dates_api.get_all(name=name,
                                          date=date,
                                          sort_field=sort_field,
                                          sort_dir=sort_dir)
        visible_dates = []
        for due_date in due_dates:
            if visible(due_date, request.current_user_id):
                due_date_model = wmodels.DueDate.from_db_model(due_date)
                due_date_model.resolve_items(due_date)
                due_date_model.resolve_permissions(due_date)
                visible_dates.append(due_date_model)

        response.headers['X-Total'] = str(len(visible_dates))

        return visible_dates

    @decorators.db_exceptions
    @secure(checks.authenticated)
    @wsme_pecan.wsexpose(wmodels.DueDate, body=wmodels.DueDate)
    def post(self, due_date):
        """Create a new due date.

        :param due_date: A due date within the request body.

        """
        due_date_dict = due_date.as_dict()
        user_id = request.current_user_id

        if duedate.creator_id and due_date.creator_id != user_id:
            abort(400, _("You can't select the creator of a due date."))
        due_date_dict.update({'creator_id': user_id})
        owners = due_date_dict.pop('owners')
        viewers = due_date_dict.pop('viewers')
        if not owners:
            owners = [user_id]
        if not viewers:
            viewers = []

        created_due_date = due_dates_api.create(due_date_dict)

        edit_permission = {
            'name': 'edit_due_date_%d' % created_due_date.id,
            'codename': 'edit_date',
            'users': owners
        }
        view_permission = {
            'name': 'view_due_date_%d' % created_due_date.id,
            'codename': 'view_date',
            'users': viewers
        }
        due_dates_api.create_permission(created_due_date.id, edit_permission)
        due_dates_api.create_permission(created_due_date.id, view_permission)

        return wmodels.DueDate.from_db_model(created_due_date)

    @decorators.db_exceptions
    @secure(checks.authenticated)
    @wsme_pecan.wsexpose(wmodels.DueDate, int, body=wmodels.DueDate)
    def put(self, id, due_date):
        """Modify a due date.

        :param id: The ID of the due date to edit.
        :param due_date: The new due date within the request body.

        """
        if not editable(due_dates_api.get(id), request.current_user_id):
            raise exc.NotFound(_("Due date %s not found") % id)

        due_date_dict = due_date.as_dict(omit_unset=True)
        updated_due_date = due_dates_api.update(id, due_date_dict)

        if visible(updated_due_date, request.current_user_id):
            due_date_model = wmodels.DueDate.from_db_model(updated_due_date)
            due_date_model.resolve_items(updated_due_date)
            due_date_model.resolve_permissions(updated_due_date)
            return due_date_model
        else:
            raise exc.NotFound(_("Due date %s not found") % id)

    permissions = PermissionsController()
