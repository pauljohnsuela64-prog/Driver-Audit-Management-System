from desktop.components.common import StatePanel


class Dashboard(StatePanel):
    def __init__(self,parent,app):
        super().__init__(parent,'Dashboard','Read-only audit workspace')
