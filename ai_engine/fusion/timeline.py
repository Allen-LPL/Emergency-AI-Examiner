class Timeline:
    def __init__(self):
        self.events: list[dict] = []

    def add_event(
        self,
        time: float,
        event_type: str,
        source: str,
        actor: str | None = None,
        confidence: float = 1.0,
        data: dict | None = None,
    ):
        self.events.append(
            {
                "time": time,
                "event_type": event_type,
                "source": source,
                "actor": actor,
                "confidence": confidence,
                "data": data or {},
            }
        )
        self.events.sort(key=lambda e: e["time"])

    def add_events(self, events: list[dict]):
        for ev in events:
            self.add_event(
                time=ev.get("time", 0.0),
                event_type=ev.get("event_type", "unknown"),
                source=ev.get("source", "unknown"),
                actor=ev.get("actor"),
                confidence=ev.get("confidence", 1.0),
                data=ev.get("data"),
            )

    def get_events(
        self,
        start: float | None = None,
        end: float | None = None,
        source: str | None = None,
        event_type: str | None = None,
    ) -> list[dict]:
        filtered = self.events
        if start is not None:
            filtered = [e for e in filtered if e["time"] >= start]
        if end is not None:
            filtered = [e for e in filtered if e["time"] <= end]
        if source is not None:
            filtered = [e for e in filtered if e["source"] == source]
        if event_type is not None:
            filtered = [e for e in filtered if e["event_type"] == event_type]
        return filtered

    def find_first_event(self, event_type: str) -> dict | None:
        for ev in self.events:
            if ev["event_type"] == event_type:
                return ev
        return None

    def find_events_by_type(self, event_type: str) -> list[dict]:
        return [e for e in self.events if e["event_type"] == event_type]

    def find_event_near(
        self, event_type: str, center_time: float, window: float = 5.0
    ) -> dict | None:
        """
        在中心时间点附近窗口内查找最近事件。

        参数:
            event_type: 事件类型
            center_time: 中心时间点（秒）
            window: 时间窗口半径（秒）

        返回:
            窗口内最近的匹配事件，若不存在则返回空值
        """
        candidates = [
            e
            for e in self.events
            if e["event_type"] == event_type and abs(e["time"] - center_time) <= window
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda e: abs(e["time"] - center_time))

    def find_events_near(
        self, event_type: str, center_time: float, window: float = 5.0
    ) -> list[dict]:
        """在时间窗口内查找全部指定类型事件。"""
        return [
            e
            for e in self.events
            if e["event_type"] == event_type and abs(e["time"] - center_time) <= window
        ]

    def to_list(self) -> list[dict]:
        return list(self.events)

    def get_duration(self) -> float:
        if not self.events:
            return 0.0
        return self.events[-1]["time"] - self.events[0]["time"]

    def detect_phases(self) -> dict[str, dict]:
        phases = {}

        arrival_event = self.find_first_event("equipment_placement")
        if not arrival_event:
            arrival_event = self.find_first_event("kneeling")

        arrival_time = arrival_event["time"] if arrival_event else 0.0

        if self.events:
            phases["phase1_before_arrival"] = {
                "start_time": self.events[0]["time"],
                "end_time": arrival_time,
            }

        compression_event = self.find_first_event("chest_compression")
        if compression_event:
            phases["phase2_arrival_step1"] = {
                "start_time": arrival_time,
                "end_time": compression_event["time"] + 5,
            }

        ecg_events = self.find_events_by_type("ecg_sign")
        if ecg_events:
            phases["phase3_arrival_step2"] = {
                "start_time": compression_event["time"]
                if compression_event
                else arrival_time,
                "end_time": ecg_events[0]["time"] + 5,
            }

        defib_events = [e for e in self.events if "defib" in e.get("event_type", "")]
        if defib_events:
            phases["phase4_arrival_step3"] = {
                "start_time": ecg_events[0]["time"] if ecg_events else arrival_time,
                "end_time": defib_events[-1]["time"] + 5,
            }

        handover_events = self.find_events_by_type("compression_handover")
        if handover_events:
            phases["phase5_arrival_step4"] = {
                "start_time": defib_events[-1]["time"]
                if defib_events
                else arrival_time,
                "end_time": handover_events[0]["time"] + 5,
            }

        transfer_events = self.find_events_by_type("transfer_consent")
        end_time = self.events[-1]["time"] if self.events else 0
        if transfer_events or self.events:
            phases["phase6_arrival_step5"] = {
                "start_time": handover_events[0]["time"]
                if handover_events
                else arrival_time,
                "end_time": end_time,
            }

        return phases
