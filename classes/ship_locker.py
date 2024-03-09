# import the mutex lock
from threading import Lock, current_thread
from datetime import datetime, timedelta


class ShipLocker:
    _ships = {}

    def __new__(self):
        if not hasattr(self, "instance"):
            self.instance = super().__new__(self)

        return self.instance

    def __init__(self):
        self._ships = {}
        self.lock = Lock()

    def lock_ship(self, ship_name: str, lock_duration: int, lock_id: str = None):
        if not lock_id:
            lock_id = current_thread().ident
        with self.lock:
            if ship_name not in self._ships:
                self._ships[ship_name] = None
            lock = self._ships[ship_name]
            if lock and lock.seconds_remaining > 0 and lock.lock_id != lock_id:
                return False
            else:
                self._ships[ship_name] = ShipLock(ship_name, lock_id, lock_duration)
            return True

    def do_i_have_the_lock(self, ship_name: str, lock_id: str):
        with self.lock:
            if ship_name in self._ships:
                lock = self._ships[ship_name]
                if lock and lock.lock_id == lock_id:
                    return True
            return False

    def is_ship_locked(self, ship_name: str):
        with self.lock:
            if ship_name in self._ships:
                lock = self._ships[ship_name]
                if lock and lock.seconds_remaining > 0:
                    return True
                else:
                    self._ships[ship_name] = None
                    return False
            else:
                return False

    def when_does_lock_expire(self, ship_name: str) -> int:
        with self.lock:
            if ship_name in self._ships:
                lock = self._ships[ship_name]
                if lock:
                    return lock.seconds_remaining
                else:
                    self._ships[ship_name] = None
                    return 0
            else:
                return None

    def unlock_early(self, ship_name: str, lock_id: str = None, force=False):
        if not lock_id:
            lock_id = current_thread().ident
        with self.lock:
            if ship_name in self._ships and self._ships[ship_name]:

                if self._ships[ship_name].lock_id == lock_id or force:
                    self._ships[ship_name] = None
                    return True
                else:
                    return False
            return True


class ShipLock:
    def __init__(self, ship_name: str, lock_id: str, lock_duration: int):
        self.ship_name = ship_name
        self.lock_id = lock_id
        self.lock_expiration = datetime.now() + timedelta(seconds=lock_duration)

    @property
    def seconds_remaining(self):
        return (self.lock_expiration - datetime.now()).seconds
