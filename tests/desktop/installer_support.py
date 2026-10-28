"""Pure postcondition shared by native installer acceptance and its race regression."""


def uninstall_complete(target,desktop,menu,has_registration):
    return not (has_registration() or desktop.exists() or menu.exists()
                or (target/'BHLIAudit.exe').exists() or (target/'unins000.exe').exists())
