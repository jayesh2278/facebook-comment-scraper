import csv
import json
import os
import re

import scrapy


class FacebookCommentsSpider(scrapy.Spider):
    name = "facebook_comments"
    allowed_domains = ["facebook.com", "www.facebook.com"]

    GRAPHQL = "https://www.facebook.com/api/graphql/"


    # =========================
    # POST INFORMATION
    # =========================

    POST_URL = "https://www.facebook.com/share/p/19U9C4yjyX/"
    POST_ID = "Meenakshi_Chaudhary"
    POST_FEEDBACK_ID = None

    # =========================
    # FACEBOOK COOKIES
    # =========================
    #
    # If you need login/session cookies,
    # put them here.
    #
    # Example:
    #
    # COOKIES = {
    #     "c_user": "123456789",
    #     "xs": "....",
    # }
    #

    COOKIES = {}

    # =========================
    # HEADERS
    # =========================

    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/x-www-form-urlencoded",
    }


    SHARE_HEADERS = {
        "accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,image/webp,"
            "image/apng,*/*;q=0.8,"
            "application/signed-exchange;v=b3;q=0.7"
        ),
        "sec-fetch-site": "same-origin",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/153.0.0.0 Safari/537.36"
        ),
    }

    # =========================
    # START
    # =========================

    async def start(self):

        yield scrapy.Request(
            url=self.POST_URL,
            method="GET",
            headers=self.SHARE_HEADERS,
            cookies=self.COOKIES,
            callback=self.parse_share_page,
        )

    def parse_share_page(self, response):

        patterns = [
            r'\{\\"associated_group\\":null,\\"id\\":\\"(.*?)\\"',
            r'\{"associated_group":null,"id":"(.*?)"',
        ]

        match = None

        for pattern in patterns:
            match = re.search(pattern, response.text)

            if match:
                break

        if not match:
            self.logger.error("POST_FEEDBACK_ID not found.")
            return

        self.POST_FEEDBACK_ID = match.group(1)

        self.logger.info(f"POST_FEEDBACK_ID: {self.POST_FEEDBACK_ID}")

        yield self.make_comments_request(
            feedback_id=self.POST_FEEDBACK_ID,
            cursor=None,
        )

    # =========================
    # COMMENTS PAYLOAD
    # =========================

    def comments_payload(self, feedback_id, cursor=None):
        """
        Create Facebook GraphQL payload for comments.
        """

        user_id = self.COOKIE_USER_ID()

        variables = {
            "commentsAfterCount": -1,
            "commentsAfterCursor": cursor,
            "commentsBeforeCount": None,
            "commentsBeforeCursor": None,
            "commentsIntentToken": "RANKED_UNFILTERED_CHRONOLOGICAL_REPLIES_INTENT_V1",
            "feedLocation": "POST_PERMALINK_DIALOG",
            "focusCommentID": None,
            "scale": 1,
            "useDefaultActor": False,
            "id": feedback_id,
            "__relay_internal__pv__CometUFICommentAutoTranslationTyperelayprovider": "AUTO_TRANSLATE",
            "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
            "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": True,
            "__relay_internal__pv__IsWorkUserrelayprovider": False,
        }

        return {
            "av": user_id,
            "__user": user_id,
            "__a": "1",
            # If you have an fb_dtsg token,
            # put it here.
            "fb_dtsg": "",
            "fb_api_caller_class": "RelayModern",
            "server_timestamps": "true",
            "doc_id": "27806180149070312",
            "variables": json.dumps(variables, separators=(",", ":")),
        }

    # =========================
    # REPLIES PAYLOAD
    # =========================

    def replies_payload(self, comment_feedback_id, expansion_token):
        """
        Create Facebook GraphQL payload for replies.
        """

        user_id = self.COOKIE_USER_ID()

        variables = {
            "clientKey": None,
            "expansionToken": expansion_token,
            "feedLocation": "POST_PERMALINK_DIALOG",
            "focusCommentID": None,
            "scale": 2,
            "useDefaultActor": False,
            "id": comment_feedback_id,
            "__relay_internal__pv__CometUFICommentAutoTranslationTyperelayprovider": "AUTO_TRANSLATE",
            "__relay_internal__pv__CometUFICommentAvatarStickerAnimatedImagerelayprovider": False,
            "__relay_internal__pv__CometUFICommentActionLinksRewriteEnabledrelayprovider": True,
            "__relay_internal__pv__IsWorkUserrelayprovider": False,
        }

        return {
            "av": user_id,
            "__user": user_id,
            "__a": "1",
            "fb_dtsg": "",
            "fb_api_caller_class": "RelayModern",
            "server_timestamps": "true",
            "doc_id": "26570577339199586",
            "variables": json.dumps(variables, separators=(",", ":")),
        }

    # =========================
    # USER ID FROM COOKIE
    # =========================

    def COOKIE_USER_ID(self):
        """
        Get c_user from cookies.

        If no c_user cookie exists,
        return 0.
        """

        return self.COOKIES.get("c_user", "0")

    # =========================
    # COMMENTS REQUEST
    # =========================

    def make_comments_request(self, feedback_id, cursor=None):
        """
        Create Scrapy request for comments.
        """

        headers = {
            **self.BASE_HEADERS,
            "x-fb-friendly-name": "CommentsListComponentsPaginationQuery",
        }

        return scrapy.FormRequest(
            url=self.GRAPHQL,
            method="POST",
            headers=headers,
            formdata=self.comments_payload(feedback_id, cursor),
            cookies=self.COOKIES,
            callback=self.parse_comments,
            errback=self.request_error,
            # Store information for callback
            cb_kwargs={
                "feedback_id": feedback_id,
                "cursor": cursor,
            },
        )

    # =========================
    # PARSE COMMENTS
    # =========================

    def parse_comments(self, response, feedback_id, cursor):
        """
        Parse one page of comments.
        """

        self.logger.info(f"Comments response received | cursor={cursor}")

        try:
            data = self.fb_json(response.text)

        except Exception as e:
            self.logger.error(f"JSON parsing failed: {e}")

            self.logger.error(response.text[:1000])

            return

        # ---------------------------------
        # Locate comments
        # ---------------------------------

        comments_block = (
            data.get("data", {})
            .get("node", {})
            .get("comment_rendering_instance_for_feed_location", {})
            .get("comments", {})
        )

        edges = comments_block.get("edges", [])

        if not edges:
            self.logger.info("No more comments.")

            self.save_output()

            return

        # ---------------------------------
        # Process comments
        # ---------------------------------

        for edge in edges:

            node = edge.get("node", {})

            feedback = node.get("feedback", {})

            # -----------------------------
            # Parent post information
            # -----------------------------

            if self.post_info is None:

                parent_post_story = (
                    node.get("comet_comment_author_name_and_badges_renderer", {})
                    .get("comment", {})
                    .get("parent_post_story", {})
                )

                if not parent_post_story:

                    parent_post_story = node.get("parent_post_story", {})

                if parent_post_story:

                    self.post_info = {
                        "post_story_id": parent_post_story.get("id"),
                        "media_id": None,
                    }

                    attachments = parent_post_story.get("attachments", [])

                    for attachment in attachments:

                        media = attachment.get("media", {})

                        if media and media.get("id"):

                            self.post_info["media_id"] = media.get("id")

                            break

                    self.logger.info(f"Post info: {self.post_info}")

            # -----------------------------
            # Reaction count
            # -----------------------------

            reactors = feedback.get("reactors", {})

            reaction_count = reactors.get("count_reduced", "0")

            # -----------------------------
            # Comment data
            # -----------------------------

            comment = {
                "text": (node.get("body") or {}).get("text", ""),
                "reaction_count": reaction_count,
                "_feedback_id": feedback.get("id"),
                "_expansion_token": (feedback.get("expansion_info") or {}).get(
                    "expansion_token"
                ),
                "replies": [],
            }

            # Save comment temporarily
            self.comments.append(comment)

            # -----------------------------
            # Fetch replies
            # -----------------------------

            feedback_id_for_reply = comment.get("_feedback_id")

            expansion_token = comment.get("_expansion_token")

            if feedback_id_for_reply and expansion_token:

                yield self.make_replies_request(comment)

            else:

                self.logger.warning("Comment has no reply information.")

        # ---------------------------------
        # Next comment page
        # ---------------------------------

        page_info = comments_block.get("page_info", {})
        print("page_info:==>", page_info)

        next_cursor = page_info.get("end_cursor")
        print("Next cursor:", next_cursor)

        # has_next_page = page_info.get("has_next_page")
        if next_cursor:

            self.logger.info("Fetching next comments page...")

            yield self.make_comments_request(feedback_id, next_cursor)

        else:

            self.logger.info("No next cursor.")

            # save full json

            print("JSON saved successfully")

            self.save_output()

    # =========================
    # REPLIES REQUEST
    # =========================

    def make_replies_request(self, comment):

        headers = {
            **self.BASE_HEADERS,
            "x-fb-friendly-name": "Depth1CommentsListPaginationQuery",
        }

        return scrapy.FormRequest(
            url=self.GRAPHQL,
            method="POST",
            headers=headers,
            formdata=self.replies_payload(
                comment["_feedback_id"],
                comment["_expansion_token"],
            ),
            cookies=self.COOKIES,
            callback=self.parse_replies,
            errback=self.request_error,
            cb_kwargs={"comment_feedback_id": comment["_feedback_id"]},
        )

    # =========================
    # PARSE REPLIES
    # =========================

    def parse_replies(self, response, comment_feedback_id):

        try:

            data = self.fb_json(response.text)

        except Exception as e:

            self.logger.error(f"Reply JSON parsing failed: {e}")

            return

        # ---------------------------------
        # Find replies
        # ---------------------------------

        edges = (
            data.get("data", {})
            .get("node", {})
            .get("replies_connection", {})
            .get("edges", [])
        )

        replies = []

        for edge in edges:

            node = edge.get("node", {})

            feedback = node.get("feedback", {})

            reactors = feedback.get("reactors", {})

            reaction_count = reactors.get("count_reduced", "0")

            replies.append(
                {
                    "text": (node.get("body") or {}).get("text", ""),
                    "reaction_count": reaction_count,
                }
            )

        # ---------------------------------
        # Find original comment
        # ---------------------------------

        for comment in self.comments:

            if comment.get("_feedback_id") == comment_feedback_id:

                comment["replies"] = replies

                break

        self.logger.info(f"Replies found: {len(replies)}")

    # =========================
    # FACEBOOK JSON PARSER
    # =========================

    def fb_json(self, response_text):
        """
        Facebook may return:

        for (;;);
        {JSON}

        Remove the prefix and parse JSON.
        """

        text = response_text.strip()

        text = text.removeprefix("for (;;);")

        # Facebook may return multiple lines.
        # Try first JSON line first.

        first_line = text.split("\n")[0].strip()

        return json.loads(first_line)

    # =========================
    # ERROR HANDLER
    # =========================

    def request_error(self, failure):

        self.logger.error(f"Request failed: {failure}")

    # =========================
    # SAVE JSON
    # =========================

    def save_output(self):

        output = {
            "post_info": self.post_info,
            "comments": self.comments,
        }

        directory = os.path.join("Output", self.POST_ID)

        os.makedirs(directory, exist_ok=True)

        output_file = os.path.join(directory, f"{self.POST_ID}.json")

        with open(output_file, "w", encoding="utf-8") as f:

            json.dump(output, f, ensure_ascii=False, indent=2)

        self.logger.info(f"Saved: {output_file}")

        # Also export the comments as CSV, next to the JSON file.
        self.save_csv(directory)

    # =========================
    # SAVE CSV
    # =========================

    def save_csv(self, directory):
        """
        Export only the comment data to CSV.

        One row per top level comment.
        Replies are joined into a single column.
        Post information is not included.
        """

        output_file = os.path.join(directory, f"{self.POST_ID}.csv")

        fieldnames = [
            "comment_id",
            "text",
            "reaction_count",
            "reply_count",
            "replies",
        ]

        # utf-8-sig so Excel renders non ASCII comment text correctly.
        with open(output_file, "w", encoding="utf-8-sig", newline="") as f:

            writer = csv.DictWriter(f, fieldnames=fieldnames)

            writer.writeheader()

            for index, comment in enumerate(self.comments, start=1):

                replies = comment.get("replies") or []

                writer.writerow(
                    {
                        "comment_id": index,
                        "text": comment.get("text", ""),
                        "reaction_count": comment.get("reaction_count", "0"),
                        "reply_count": len(replies),
                        "replies": " | ".join(
                            (reply.get("text") or "") for reply in replies
                        ),
                    }
                )

        self.logger.info(f"Saved: {output_file}")

    # =========================
    # INITIAL VARIABLES
    # =========================

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.comments = []

        self.post_info = None
