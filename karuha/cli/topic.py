from ptcmd import auto_argument

from .app import App


class TopicApp(App):
    """
    Topic management.
    """

    @auto_argument
    def do_topic(self) -> None:
        """
        Topic management.
        """
        pass
    
    
