# Copyright (c) 2013 Mirantis Inc.
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

from oslo.config import cfg
from pecan import abort
from pecan import expose
from pecan import request
from pecan import response
from pecan import rest
from pecan.secure import secure
import wsmeext.pecan as wsme_pecan

from storyboard.api.auth import authorization_checks as checks
from storyboard.api.v1.search import search_engine
from storyboard.api.v1.tags import TagsController
from storyboard.api.v1.timeline import CommentsController
from storyboard.api.v1.timeline import TimeLineEventsController
from storyboard.api.v1 import validations
from storyboard.api.v1 import wmodels
from storyboard.common import decorators
from storyboard.common import exception as exc
from storyboard.db.api import stories as stories_api
from storyboard.db.api import timeline_events as events_api
from storyboard.openstack.common.gettextutils import _  # noqa


CONF = cfg.CONF

SEARCH_ENGINE = search_engine.get_engine()


class StoriesController(rest.RestController):
    """Manages operations on stories."""

    _custom_actions = {"search": ["GET"]}

    validation_post_schema = validations.STORIES_POST_SCHEMA
    validation_put_schema = validations.STORIES_PUT_SCHEMA

    @decorators.db_exceptions
    @secure(checks.guest)
    @wsme_pecan.wsexpose(wmodels.Story, int)
    def get_one(self, story_id):
        """Retrieve details about one story.

        :param story_id: An ID of the story.
        """
        story = stories_api.story_get(story_id)

        if story:
            return wmodels.Story.from_db_model(story)
        else:
            raise exc.NotFound(_("Story %s not found") % story_id)

    @decorators.db_exceptions
    @secure(checks.guest)
    @wsme_pecan.wsexpose([wmodels.Story], unicode, unicode, [unicode], int,
                         int, int, [unicode], int, int, unicode, unicode,
                         unicode)
    def get_all(self, title=None, description=None, status=None,
                assignee_id=None, project_group_id=None, project_id=None,
                tags=None, marker=None, limit=None, tags_filter_type='all',
                sort_field='id', sort_dir='asc'):
        """Retrieve definitions of all of the stories.

        :param title: A string to filter the title by.
        :param description: A string to filter the description by.
        :param status: Only show stories with this particular status.
        :param assignee_id: filter stories by who they are assigned to.
        :param project_group_id: filter stories by project group.
        :param project_id: filter stories by project ID.
        :param tags: a list of tags to filter by.
        :param marker: The resource id where the page should begin.
        :param limit: The number of stories to retrieve.
        :param tags_filter_type: type of tags filter.
        :param sort_field: The name of the field to sort on.
        :param sort_dir: sort direction for results (asc, desc).
        """

        # Boundary check on limit.
        if limit is None:
            limit = CONF.page_size_default
        limit = min(CONF.page_size_maximum, max(1, limit))

        # Resolve the marker record.
        marker_story = stories_api.story_get(marker)

        stories = stories_api \
            .story_get_all(title=title,
                           description=description,
                           status=status,
                           assignee_id=assignee_id,
                           project_group_id=project_group_id,
                           project_id=project_id,
                           tags=tags,
                           marker=marker_story,
                           tags_filter_type=tags_filter_type,
                           limit=limit, sort_field=sort_field,
                           sort_dir=sort_dir)
        story_count = stories_api \
            .story_get_count(title=title,
                             description=description,
                             status=status,
                             assignee_id=assignee_id,
                             project_group_id=project_group_id,
                             project_id=project_id,
                             tags=tags,
                             tags_filter_type=tags_filter_type)

        # Apply the query response headers.
        response.headers['X-Limit'] = str(limit)
        response.headers['X-Total'] = str(story_count)
        if marker_story:
            response.headers['X-Marker'] = str(marker_story.id)

        return [wmodels.Story.from_db_model(s) for s in stories]

    @decorators.db_exceptions
    @secure(checks.authenticated)
    @wsme_pecan.wsexpose(wmodels.Story, body=wmodels.Story)
    def post(self, story):
        """Create a new story.

        :param story: a story within the request body.
        """
        story_dict = story.as_dict()

        user_id = request.current_user_id

        if story.creator_id and story.creator_id != user_id:
            abort(400, _("You can't select author of story."))

        story_dict.update({"creator_id": user_id})

        if not "tags" in story_dict or not story_dict["tags"]:
            story_dict["tags"] = []

        created_story = stories_api.story_create(story_dict)

        events_api.story_created_event(created_story.id, user_id, story.title)

        return wmodels.Story.from_db_model(created_story)

    @decorators.db_exceptions
    @secure(checks.authenticated)
    @wsme_pecan.wsexpose(wmodels.Story, int, body=wmodels.Story)
    def put(self, story_id, story):
        """Modify this story.

        :param story_id: An ID of the story.
        :param story: a story within the request body.
        """

        original_story = stories_api.story_get_simple(story_id)

        if story.creator_id and story.creator_id != original_story.creator_id:
            abort(400, _("You can't change author of story."))

        updated_story = stories_api.story_update(
            story_id,
            story.as_dict(omit_unset=True))

        if updated_story:
            user_id = request.current_user_id
            events_api.story_details_changed_event(story_id, user_id,
                                                   updated_story.title)

            return wmodels.Story.from_db_model(updated_story)
        else:
            raise exc.NotFound(_("Story %s not found") % story_id)

    @decorators.db_exceptions
    @secure(checks.superuser)
    @wsme_pecan.wsexpose(wmodels.Story, int, status_code=204)
    def delete(self, story_id):
        """Delete this story.

        :param story_id: An ID of the story.
        """
        stories_api.story_delete(story_id)

    comments = CommentsController()
    events = TimeLineEventsController()
    tags = TagsController()

    @decorators.db_exceptions
    @secure(checks.guest)
    @wsme_pecan.wsexpose([wmodels.Story], unicode, unicode, int, int)
    def search(self, q="", marker=None, limit=None):
        """The search endpoint for stories.

        :param q: The query string.
        :return: List of Stories matching the query.
        """

        stories = SEARCH_ENGINE.stories_query(q=q,
                                              marker=marker,
                                              limit=limit)

        return [wmodels.Story.from_db_model(story) for story in stories]

    @expose()
    def _route(self, args, request):
        if request.method == 'GET' and len(args) > 0:
            # It's a request by a name or id
            something = args[0]

            if something == "search":
                # Request to a search endpoint
                return self.search, args

            if something == "get_by_tags":
                # Request by a list of tags
                return self.get_by_tags, args

        return super(StoriesController, self)._route(args, request)
