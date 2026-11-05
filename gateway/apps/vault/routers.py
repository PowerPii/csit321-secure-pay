class VaultRouter:
    """Send vault models to the "vault" database alias, which uses a separate DB role."""

    app_label = "vault"

    def db_for_read(self, model, **hints):
        return "vault" if model._meta.app_label == self.app_label else None

    def db_for_write(self, model, **hints):
        return "vault" if model._meta.app_label == self.app_label else None

    def allow_relation(self, obj1, obj2, **hints):
        labels = {obj1._meta.app_label, obj2._meta.app_label}
        if self.app_label in labels and len(labels) > 1:
            return False
        return None

    def allow_migrate(self, db, app_label, **hints):
        if app_label == self.app_label:
            return db == "vault"
        return None if db == "default" else False
