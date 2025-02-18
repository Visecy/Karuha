from functools import partial
from typing import Any, Awaitable, Callable, Coroutine, Mapping, Optional, TypeVar
from typing_extensions import Self

from google.protobuf.message import Message
from tinode_grpc import pb

from .. import bot
from ..session import BaseSession
from ..utils.proxy_propery import ProxyProperty
from ..utils.invoker import Dependency, depend_property
from .base import Event, handler_runner


def ensure_text_len(text: str, length: int = 128) -> str:
    if len(text) < length:
        return text
    tail_length = length // 4
    return f"{text[:length-tail_length]} ... {text[-tail_length:]}"


class BotEvent(Event):
    __slots__ = ["bot"]

    bot: Dependency["bot.Bot"]

    def __init__(self, bot: "bot.Bot", /) -> None:
        self.bot = bot

    def call_handler(self, handler: Callable[[Self], Coroutine]) -> Awaitable:
        return self.bot._create_task(handler_runner(self, self.bot.logger, handler))


class BotInitEvent(BotEvent):
    __slots__ = []

    async def __default_handler__(self) -> None:
        prepare_task = self.bot._create_task(self.bot._prepare_account())
        prepare_task.add_done_callback(lambda _: BotReadyEvent.new(self.bot))


class BotReadyEvent(BotEvent):
    __slots__ = []


class BotFinishEvent(BotEvent):
    __slots__ = []


bot.Bot.initialize_event_callback = BotInitEvent.new
bot.Bot.finalize_event_callback = BotFinishEvent.new_and_wait


T = TypeVar("T")
ProxyPropertyType = Dependency[ProxyProperty[T]]
SessionProperty = depend_property(lambda ev: BaseSession(ev.bot, ev.topic).bind_task())


# Server Event Part
# =========================


ServerMessageProperty = partial(ProxyProperty, "server_message")


class ServerEvent(BotEvent):
    """base class for all events from server"""

    __slots__ = ["server_message"]

    server_message: Dependency[Message]

    def __init__(self, bot: "bot.Bot", message: Message) -> None:
        super().__init__(bot)
        self.server_message = message

    def __init_subclass__(cls, on_field: str, **kwds: Any) -> None:
        super().__init_subclass__(**kwds)
        bot.Bot.server_event_callbacks[on_field].append(cls.new)


class DataEvent(ServerEvent, on_field="data"):
    """
    Content published in the topic. These messages are the only messages persisted in database; `{data}` messages are
    broadcast to all topic subscribers with an `R` permission.

    ```js
    data: {
        topic: "grp1XUtEhjv6HND", // string, topic which distributed this message,
                                    // always present
        from: "usr2il9suCbuko", // string, id of the user who published the
                                // message; could be missing if the message was
                                // generated by the server
        head: { key: "value", ... }, // set of string key-value pairs, passed
                                    // unchanged from {pub}, optional
        ts: "2015-10-06T18:07:30.038Z", // string, timestamp
        seq: 123, // integer, server-issued sequential ID
        content: { ... } // object, application-defined content exactly as published
                    // by the user in the {pub} message
    }
    ```

    Data messages have a `seq` field which holds a sequential numeric ID generated by the server.
    The IDs are guaranteed to be unique within a topic. IDs start from 1 and sequentially increment
    with every successful [{pub}](https://github.com/tinode/chat/blob/master/docs/API.md#pub) message received by the topic.

    See [Format of Content](https://github.com/tinode/chat/blob/master/docs/API.md#format-of-content)
    for `content` format considerations.

    See [{pub}](https://github.com/tinode/chat/blob/master/docs/API.md#pub) message
    for the possible values of the `head` field.
    """

    __slots__ = []

    server_message: pb.ServerData

    topic: ProxyPropertyType[str] = ServerMessageProperty()
    from_user_id: ProxyPropertyType[str] = ServerMessageProperty()
    timestamp: ProxyPropertyType[int] = ServerMessageProperty()
    deleted_at: ProxyPropertyType[int] = ServerMessageProperty()
    seq_id: ProxyPropertyType[int] = ServerMessageProperty()
    head: ProxyPropertyType[Mapping[str, bytes]] = ServerMessageProperty()
    content: ProxyPropertyType[bytes] = ServerMessageProperty()
    session = SessionProperty

    @depend_property
    def text(self) -> str:
        return self.content.decode(errors="ignore")


class CtrlEvent(ServerEvent, on_field="ctrl"):
    """
    Generic response indicating an error or a success condition. The message is sent to the originating session.

    ```js
    ctrl: {
        id: "1a2b3", // string, client-provided message id, optional
        topic: "grp1XUtEhjv6HND", // string, topic name, if this is a response in context
                                    // of a topic, optional
        code: 200, // integer, code indicating success or failure of the request, follows
                    // the HTTP status codes model, always present
        text: "OK", // string, text with more details about the result, always present
        params: { ... }, // object, generic response parameters, context-dependent,
                        // optional
        ts: "2015-10-06T18:07:30.038Z", // string, timestamp
    }
    ```
    """

    __slots__ = []

    server_message: pb.ServerCtrl

    id: ProxyPropertyType[str] = ServerMessageProperty()
    topic: ProxyPropertyType[str] = ServerMessageProperty()
    code: ProxyPropertyType[int] = ServerMessageProperty()
    text: ProxyPropertyType[str] = ServerMessageProperty()
    params: ProxyPropertyType[Mapping[str, bytes]] = ServerMessageProperty()
    session = SessionProperty
    
    async def __default_handler__(self) -> None:
        tid = self.server_message.id
        self.bot._set_reply_message(tid, self.server_message)


class MetaEvent(ServerEvent, on_field="meta"):
    """
    Information about topic metadata or subscribers, sent in response to `{get}`,
    `{set}` or `{sub}` message to the originating session.

    ```js
    meta: {
        id: "1a2b3", // string, client-provided message id, optional
        topic: "grp1XUtEhjv6HND", // string, topic name, if this is a response in
                                    // context of a topic, optional
        ts: "2015-10-06T18:07:30.038Z", // string, timestamp
        desc: {
            created: "2015-10-24T10:26:09.716Z",
            updated: "2015-10-24T10:26:09.716Z",
            status: "ok", // account status; included for `me` topic only, and only if
                        // the request is sent by a root-authenticated session.
            defacs: { // topic's default access permissions; present only if the current
                    //user has 'S' permission
                auth: "JRWP", // default access for authenticated users
                anon: "N" // default access for anonymous users
            },
            acs: {  // user's actual access permissions
                want: "JRWP", // string, requested access permission
                given: "JRWP", // string, granted access permission
                mode: "JRWP" // string, combination of want and given
            },
            seq: 123, // integer, server-issued id of the last {data} message
            read: 112, // integer, ID of the message user claims through {note} message
                    // to have read, optional
            recv: 115, // integer, like 'read', but received, optional
            clear: 12, // integer, in case some messages were deleted, the greatest ID
                    // of a deleted message, optional
            trusted: { ... }, // application-defined payload assigned by the system
                            // administration
            public: { ... }, // application-defined data that's available to all topic
                            // subscribers
            private: { ...} // application-defined data that's available to the current
                            // user only
        }, // object, topic description, optional
        sub:  [ // array of objects, topic subscribers or user's subscriptions, optional
            {
                user: "usr2il9suCbuko", // string, ID of the user this subscription
                                        // describes, absent when querying 'me'.
                updated: "2015-10-24T10:26:09.716Z", // timestamp of the last change in the
                                                    // subscription, present only for
                                                    // requester's own subscriptions
                touched: "2017-11-02T09:13:55.530Z", // timestamp of the last message in the
                                                    // topic (may also include other events
                                                    // in the future, such as new subscribers)
                acs: {  // user's access permissions
                    want: "JRWP", // string, requested access permission, present for user's own
                        // subscriptions and when the requester is topic's manager or owner
                    given: "JRWP", // string, granted access permission, optional exactly as 'want'
                    mode: "JRWP" // string, combination of want and given
                },
                read: 112, // integer, ID of the message user claims through {note} message
                            // to have read, optional.
                recv: 315, // integer, like 'read', but received, optional.
                clear: 12, // integer, in case some messages were deleted, the greatest ID
                            // of a deleted message, optional.
                trusted: { ... }, // application-defined payload assigned by the system
                                    // administration
                public: { ... }, // application-defined user's 'public' object, absent when
                                // querying P2P topics.
                private: { ... } // application-defined user's 'private' object.
                online: true, // boolean, current online status of the user; if this is a
                                // group or a p2p topic, it's user's online status in the topic,
                                // i.e. if the user is attached and listening to messages; if this
                                // is a response to a 'me' query, it tells if the topic is
                                // online; p2p is considered online if the other party is
                                // online, not necessarily attached to topic; a group topic
                                // is considered online if it has at least one active
                                // subscriber.

                // The following fields are present only when querying 'me' topic

                topic: "grp1XUtEhjv6HND", // string, topic this subscription describes
                seq: 321, // integer, server-issued id of the last {data} message

                // The following field is present only when querying 'me' topic and the
                // topic described is a P2P topic
                seen: { // object, if this is a P2P topic, info on when the peer was last
                        //online
                    when: "2015-10-24T10:26:09.716Z", // timestamp
                    ua: "Tinode/1.0 (Android 5.1)" // string, user agent of peer's client
                }
            },
            ...
        ],
        tags: [ // array of tags that the topic or user (in case of "me" topic) is indexed by
            "email:alice@example.com", "tel:+1234567890"
        ],
        cred: [ // array of user's credentials
            {
                meth: "email", // string, validation method
                val: "alice@example.com", // string, credential value
                done: true     // validation status
            },
            ...
        ],
        del: {
            clear: 3, // ID of the latest applicable 'delete' transaction
            delseq: [{low: 15}, {low: 22, hi: 28}, ...], // ranges of IDs of deleted messages
        }
    }
    ```
    """

    __slots__ = []

    server_message: pb.ServerMeta

    id: ProxyPropertyType[str] = ServerMessageProperty()
    topic: ProxyPropertyType[str] = ServerMessageProperty()
    session = SessionProperty
    
    async def __default_handler__(self) -> None:
        tid = self.server_message.id
        self.bot._set_reply_message(tid, self.server_message)


class PresEvent(ServerEvent, on_field="pres"):
    """
    Tinode uses `{pres}` message to inform clients of important events.
    A separate [document](https://docs.google.com/spreadsheets/d/e/2PACX-1vStUDHb7DPrD8tF5eANLu4YIjRkqta8KOhLvcj2precsjqR40eDHvJnnuuS3bw-NcWsP1QKc7GSTYuX/pubhtml?gid=1959642482&single=true) explains all possible use cases.

    ```js
    pres: {
        topic: "me", // string, topic which receives the notification, always present
        src: "grp1XUtEhjv6HND", // string, topic or user affected by the change, always present
        what: "on", // string, action type, what's changed, always present
        seq: 123, // integer, "what" is "msg", a server-issued ID of the message,
                    // optional
        clear: 15, // integer, "what" is "del", an update to the delete transaction ID.
        delseq: [{low: 123}, {low: 126, hi: 136}], // array of ranges, "what" is "del",
                    // ranges of IDs of deleted messages, optional
        ua: "Tinode/1.0 (Android 2.2)", // string, a User Agent string identifying the client
                    // software if "what" is "on" or "ua", optional
        act: "usr2il9suCbuko",  // string, user who performed the action, optional
        tgt: "usrRkDVe0PYDOo",  // string, user affected by the action, optional
        acs: {want: "+AS-D", given: "+S"} // object, changes to access mode, "what" is "acs",
                                // optional
    }
    ```

    The following action types are currently defined:

    * on: topic or user came online
    * off: topic or user went offline
    * ua: user agent changed, for example user was logged in with one client, then logged in with another
    * upd: topic description has changed
    * tags: topic tags have changed
    * acs: access permissions have changed
    * gone: topic is no longer available, for example, it was deleted or you were unsubscribed from it
    * term: subscription to topic has been terminated, you may try to resubscribe
    * msg: a new message is available
    * read: one or more messages have been read by the recipient
    * recv: one or more messages have been received by the recipient
    * del: messages were deleted


    The `{pres}` messages are purely transient: they are not stored and no attempt is made
    to deliver them later if the destination is temporarily unavailable.

    Timestamp is not present in `{pres}` messages.
    """  # noqa

    __slots__ = []

    server_message: pb.ServerPres

    topic: ProxyPropertyType[str] = ServerMessageProperty()
    src: ProxyPropertyType[str] = ServerMessageProperty()
    what: ProxyPropertyType["pb.ServerPres.What"] = ServerMessageProperty()
    user_agent: ProxyPropertyType[str] = ServerMessageProperty()
    seq_id: ProxyPropertyType[int] = ServerMessageProperty()
    del_id: ProxyPropertyType[int] = ServerMessageProperty()
    target_user_id: ProxyPropertyType[str] = ServerMessageProperty()
    actor_user_id: ProxyPropertyType[str] = ServerMessageProperty()
    session = SessionProperty

    async def __default_handler__(self) -> None:
        msg = self.server_message
        if msg.topic != "me":
            if msg.what == pb.ServerPres.ACS:
                topic = msg.topic
                _, meta = await self.bot.get(topic, "desc")
                if meta:
                    await self.bot.set(topic, sub=pb.SetSub(mode=meta.desc.acs.given))
            return
        if msg.what == pb.ServerPres.ON:
            await self.bot.subscribe(msg.src, get="desc sub")
        elif msg.what == pb.ServerPres.MSG:
            await self.bot.subscribe(
                msg.src,
                get=pb.GetQuery(
                    what="desc sub data",
                    data=pb.GetOpts(
                        since_id=msg.seq_id
                    )
                )
            )
        elif msg.what == pb.ServerPres.OFF:
            await self.bot.leave(msg.src)
        elif msg.what == pb.ServerPres.UPD:
            await self.bot.get(msg.src, "desc")
        elif msg.what == pb.ServerPres.ACS:
            topic = msg.src
            _, meta = await self.bot.get(topic, "desc")
            if meta:
                await self.bot.set(topic, sub=pb.SetSub(mode=meta.desc.acs.given))


class InfoEvent(ServerEvent, on_field="info"):
    """
    Forwarded client-generated notification `{note}`. Server guarantees that the message complies
    with this specification and that content of `topic` and `from` fields is correct.
    The other content is copied from the `{note}` message verbatim and
    may potentially be incorrect or misleading if the originator  so desires.

    ```js
    info: {
        topic: "grp1XUtEhjv6HND", // string, topic affected, always present
        from: "usr2il9suCbuko", // string, id of the user who published the
                                // message, always present
        what: "read", // string, one of "kp", "recv", "read", "data", see client-side {note},
                        // always present
        seq: 123, // integer, ID of the message that client has acknowledged,
                    // guaranteed 0 < read <= recv <= {ctrl.params.seq}; present for recv &
                    // read
    }
    ```
    """

    __slots__ = []

    server_message: pb.ServerInfo

    topic: ProxyPropertyType[str] = ServerMessageProperty()
    from_user_id: ProxyPropertyType[str] = ServerMessageProperty()
    what: ProxyPropertyType["pb.InfoNote"] = ServerMessageProperty()
    seq_id: ProxyPropertyType[int] = ServerMessageProperty()
    src: ProxyPropertyType[str] = ServerMessageProperty()
    payload: ProxyPropertyType[bytes] = ServerMessageProperty()
    session = SessionProperty


# Client Event Part
# =========================


ClientMessageProperty = partial(ProxyProperty, "client_message")


class ClientEvent(BotEvent):
    """base class for client events
    
    NOTE: Such events will be triggered after the corresponding action is completed.
    """

    __slots__ = ["client_message", "response_message", "extra"]

    def __init__(
        self,
        bot: "bot.Bot",
        message: Message,
        response_message: Optional[Message] = None,
        extra: Optional[pb.ClientExtra] = None,
    ) -> None:
        super().__init__(bot)
        self.client_message = message
        self.response_message = response_message
        self.extra = extra

    def __init_subclass__(cls, on_field: str, **kwds: Any) -> None:
        super().__init_subclass__(**kwds)
        bot.Bot.client_event_callbacks[on_field].append(cls.new)


class LoginEvent(ClientEvent, on_field="login"):
    """
    Login is used to authenticate the current session.

    ```js
    login: {
    id: "1a2b3",     // string, client-provided message id, optional
    scheme: "basic", // string, authentication scheme; "basic",
                    // "token", and "reset" are currently supported
    secret: base64encode("username:password"), // string, base64-encoded secret for the chosen
                    // authentication scheme, required
    cred: [
        {
        meth: "email", // string, verification method, e.g. "email", "tel", "captcha", etc, required
        resp: "178307" // string, verification response, required
        },
    ...
    ],   // response to a request for credential verification, optional
    }
    ```

    Server responds to a `{login}` packet with a `{ctrl}` message.
    The `params` of the message contains the id of the logged in user as `user`.
    The `token` contains an encrypted string which can be used for authentication.
    Expiration time of the token is passed as `expires`.
    """
    __slots__ = []

    client_message: pb.ClientLogin
    response_message: Optional[pb.ServerCtrl]

    id: ProxyPropertyType[str] = ClientMessageProperty()
    scheme: ProxyPropertyType[str] = ClientMessageProperty()
    secret: ProxyPropertyType[bytes] = ClientMessageProperty()

    async def __default_handler__(self) -> None:
        if self.response_message is not None:
            code = self.response_message.code
            if code < 200 or code >= 400 and code != 409:
                # login failed
                return


class PublishEvent(ClientEvent, on_field="pub"):
    """
    The message is used to distribute content to topic subscribers.

    ```js
    pub: {
        id: "1a2b3", // string, client-provided message id, optional
        topic: "grp1XUtEhjv6HND", // string, topic to publish to, required
        noecho: false, // boolean, suppress echo (see below), optional
        head: { key: "value", ... }, // set of string key-value pairs,
                    // passed to {data} unchanged, optional
        content: { ... }  // object, application-defined content to publish
                    // to topic subscribers, required
    }
    ```

    Topic subscribers receive the `content` in the [`{data}`](#data) message.
    By default the originating session gets a copy of `{data}`
    like any other session currently attached to the topic.
    If for some reason the originating session does not want to receive
    the copy of the data it just published, set `noecho` to `true`.

    See [Format of Content](https://github.com/tinode/chat/blob/master/docs/API.md#format-of-content)
    for `content` format considerations.

    The following values are currently defined for the `head` field:

    * `attachments`: an array of paths indicating media attached to this message `["/v0/file/s/sJOD_tZDPz0.jpg"]`.
    * `auto`: `true` when the message was sent automatically, i.e. by a chatbot or an auto-responder.
    * `forwarded`: an indicator that the message is a forwarded message,
        a unique ID of the original message, `"grp1XUtEhjv6HND:123"`.
    * `mentions`: an array of user IDs mentioned (`@alice`) in the message: `["usr1XUtEhjv6HND", "usr2il9suCbuko"]`.
    * `mime`: MIME-type of the message content, `"text/x-drafty"`;
        a `null` or a missing value is interpreted as `"text/plain"`.
    * `replace`: an indicator that the message is a correction/replacement for another message,
        a topic-unique ID of the message being updated/replaced, `":123"`
    * `reply`: an indicator that the message is a reply to another message,
        a unique ID of the original message, `"grp1XUtEhjv6HND:123"`.
    * `sender`: a user ID of the sender added by the server when the message is sent
        on behalf of another user, `"usr1XUtEhjv6HND"`.
    * `thread`: an indicator that the message is a part of a conversation thread,
        a topic-unique ID of the first message in the thread, `":123"`;
        `thread` is intended for tagging a flat list of messages as opposite to creating a tree.
    * `webrtc`: a string representing the state of the video call the message represents. Possible values:
    * `"started"`: call has been initiated and being established
    * `"accepted"`: call has been accepted and established
    * `"finished"`: previously successfully established call has been ended
    * `"missed"`: call timed out before getting established
    * `"declined"`: call was hung up by the callee before getting established
    * `"busy"`: the call was declined due to the callee being in another call.
    * `"disconnected"`: call was terminated by the server for other reasons (e.g. due to an error)
    * `webrtc-duration`: a number representing a video call duration (in milliseconds).

    Application-specific fields should start with an `x-<application-name>-`.
    Although the server does not enforce this rule yet, it may start doing so in the future.

    The unique message ID should be formed as `<topic_name>:<seqId>` whenever possible, such as `"grp1XUtEhjv6HND:123"`.
    If the topic is omitted, i.e. `":123"`, it's assumed to be the current topic.
    """

    __slots__ = []

    client_message: pb.ClientPub
    response_message: Optional[pb.ServerCtrl]
    
    id: ProxyPropertyType[str] = ClientMessageProperty()
    topic: ProxyPropertyType[str] = ClientMessageProperty()
    head: ProxyPropertyType[Mapping[str, bytes]] = ClientMessageProperty()
    content: ProxyPropertyType[bytes] = ClientMessageProperty()
    session = SessionProperty
    
    async def __default_handler__(self) -> None:
        self.bot.logger.info(f"({self.topic})<= {ensure_text_len(self.text)}")

    @property
    def text(self) -> str:
        return self.content.decode(errors="ignore")
    
    @property
    def seq_id(self) -> Optional[int]:
        if self.response_message is None:
            return
        params = bot.decode_mapping(self.response_message.params)
        return params.get("seq")


class SubscribeEvent(ClientEvent, on_field="sub"):
    """
    The `{sub}` packet serves the following functions:
    * creating a new topic
    * subscribing user to an existing topic
    * attaching session to a previously subscribed topic
    * fetching topic data

    User creates a new group topic by sending `{sub}` packet with the `topic` field set
    to `new12321` (regular topic) or `nch12321` (channel) where `12321` denotes any string including an empty string.
    Server will create a topic and respond back to the session with the name of the newly created topic.

    User creates a new peer to peer topic by sending `{sub}` packet with `topic` set to peer's user ID.

    The user is always subscribed to and the session is attached to the newly created topic.

    If the user had no relationship with the topic, sending `{sub}` packet creates it.
    Subscribing means to establish a relationship between session's user and
    the topic where no relationship existed in the past.

    Joining (attaching to) a topic means for the session to start consuming content from the topic.
    Server automatically differentiates between subscribing and joining/attaching based on context:
    if the user had no prior relationship with the topic, the server subscribes the user
    then attaches the current session to the topic.
    If relationship existed, the server only attaches the session to the topic.
    When subscribing, the server checks user's access permissions against topic's access control list.
    It may grant immediate access, deny access, may generate a request for approval from topic managers.

    Server replies to the `{sub}` with a `{ctrl}`.

    The `{sub}` message may include a `get` and `set` fields which mirror `{get}` and `{set}` messages.
    If included, server will treat them as a subsequent `{set}` and `{get}` messages on the same topic. If the `get` is set,
    the reply may include `{meta}` and `{data}` messages.

    ```js
    sub: {
        id: "1a2b3",  // string, client-provided message id, optional
        topic: "me",  // topic to be subscribed or attached to
        bkg: true,    // request to attach to topic is issued by an automated agent, server should delay sending
                        // presence notifications because the agent is expected to disconnect very quickly
        // Object with topic initialisation data, new topics & new
        // subscriptions only, mirrors {set} message
        set: {
        // New topic parameters, mirrors {set desc}
            desc: {
            defacs: {
                auth: "JRWS", // string, default access for new authenticated subscribers
                anon: "N"    // string, default access for new anonymous (un-authenticated)
                            // subscribers
            }, // Default access mode for the new topic
            trusted: { ... }, // application-defined payload assigned by the system administration
            public: { ... }, // application-defined payload to describe topic
            private: { ... } // per-user private application-defined content
            }, // object, optional

            // Subscription parameters, mirrors {set sub}. 'sub.user' must be blank
            sub: {
            mode: "JRWS", // string, requested access mode, optional;
                        // default: server-defined
            }, // object, optional

            tags: [ // array of strings, update to tags (see fnd topic description), optional.
                "email:alice@example.com", "tel:1234567890"
            ],

            cred: { // update to credentials, optional.
                meth: "email", // string, verification method, e.g. "email", "tel", "recaptcha", etc.
                val: "alice@example.com", // string, credential to verify such as email or phone
                resp: "178307", // string, verification response, optional
                params: { ... } // parameters, specific to the verification method, optional
            }
        },

        get: {
            // Metadata to request from the topic; space-separated list, valid strings
            // are "desc", "sub", "data", "tags"; default: request nothing; unknown strings are
            // ignored; see {get  what} for details
            what: "desc sub data", // string, optional

            // Optional parameters for {get what="desc"}
            desc: {
            ims: "2015-10-06T18:07:30.038Z" // timestamp, "if modified since" - return
                    // public and private values only if at least one of them has been
                    // updated after the stated timestamp, optional
            },

            // Optional parameters for {get what="sub"}
            sub: {
            ims: "2015-10-06T18:07:30.038Z", // timestamp, "if modified since" - return
                    // only those subscriptions which have been modified after the stated
                    // timestamp, optional
            user: "usr2il9suCbuko", // string, return results for a single user,
                                    // any topic other than 'me', optional
            topic: "usr2il9suCbuko", // string, return results for a single topic,
                                    // 'me' topic only, optional
            limit: 20 // integer, limit the number of returned objects
            },

            // Optional parameters for {get what="data"}, see {get what="data"} for details
            data: {
            since: 123, // integer, load messages with server-issued IDs greater or equal
                    // to this (inclusive/closed), optional
            before: 321, // integer, load messages with server-issued sequential IDs less
                    // than this (exclusive/open), optional
            limit: 20, // integer, limit the number of returned objects,
                        // default: 32, optional
            } // object, optional
        }
    }
    ```
    """

    __slots__ = []

    client_message: pb.ClientSub
    response_message: Optional[pb.ServerCtrl]

    id: ProxyPropertyType[str] = ClientMessageProperty()
    session = SessionProperty

    @property
    def topic(self) -> str:
        if self.response_message is not None and self.response_message.topic:
            return self.response_message.topic
        return self.client_message.topic


class LeaveEvent(ClientEvent, on_field="leave"):
    """
    This is a counterpart to `{sub}` message. It also serves two functions:
    * leaving the topic without unsubscribing (`unsub=false`)
    * unsubscribing (`unsub=true`)

    Server responds to `{leave}` with a `{ctrl}` packet.
    Leaving without unsubscribing affects just the current session.
    Leaving with unsubscribing will affect all user's sessions.

    ```js
    leave: {
        id: "1a2b3",  // string, client-provided message id, optional
        topic: "grp1XUtEhjv6HND",   // string, topic to leave, unsubscribe, or
                                    // delete, required
        unsub: true // boolean, leave and unsubscribe, optional, default: false
    }
    ```
    """

    __slots__ = []

    client_message: pb.ClientLeave
    response_message: Optional[pb.ServerCtrl]

    id: ProxyPropertyType[str] = ClientMessageProperty()
    unsub: ProxyPropertyType[bool] = ClientMessageProperty()
    session = SessionProperty

    @property
    def topic(self) -> str:
        if self.response_message is not None and self.response_message.topic:
            return self.response_message.topic
        return self.client_message.topic
