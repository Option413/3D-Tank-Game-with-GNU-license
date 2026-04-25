from __future__ import annotations

from dataclasses import dataclass
import math
import random

from direct.gui.DirectGui import DirectButton, DirectFrame
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from direct.showbase.ShowBaseGlobal import globalClock
from panda3d.core import AmbientLight, DirectionalLight, NodePath, TextNode, Vec3, Vec4

from Tanks.M3Grant import M3Grant
from Tanks.M4Sherman import M4Sherman
from Tanks.PanzerIV import PanzerIV
from Tanks.TankBase import Tank
from Tanks.TigerI import TigerI


ARENA_X = 34.0
ARENA_Y = 28.0
PLAYER_MOVE_SPEED = 10.0
PLAYER_TURN_SPEED = 95.0
TURRET_TURN_SPEED = 115.0
SHELL_SPEED = 36.0
PLAYER_FIRE_COOLDOWN = 1.1
PLAYER_SPECIAL_COOLDOWN = 4.5
PLAYER_REPAIR_COOLDOWN = 8.0
ENEMY_FIRE_COOLDOWN = 1.7
ENEMY_SPECIAL_COOLDOWN = 5.6
DETECTION_RANGE = 34.0
DETECTION_FOV = 100.0
MEMORY_TIME = 9.0
AI_PATROL_SPEED = 5.0
AI_CHASE_SPEED = 7.8
AI_HULL_TURN_RATE = 88.0
AI_TURRET_TURN_RATE = 132.0
AI_FIRE_ANGLE_TOLERANCE = 18.0
AI_SPECIAL_CHANCE = 0.34
INFANTRY_RANGE = 18.0
INFANTRY_FIRE_COOLDOWN = 2.3
RIFLE_FIRE_COOLDOWN = 3.1
AIR_SUPPORT_BASE_COOLDOWN = 14.0
AIRCRAFT_SPEED = 22.0


@dataclass
class TankView:
    tank: Tank
    root: NodePath
    hull: NodePath
    turret_pivot: NodePath
    barrel_tip: NodePath
    label_node: TextNode
    label_path: NodePath
    color: tuple[float, float, float, float]

    def refresh(self, highlight: Vec4 | None = None) -> None:
        special_state = "Ready" if self.tank.special_ready else "Used"
        self.label_node.setText(
            f"{self.tank.name}\nHP {self.tank.health}/{self.tank.max_health}\nSpecial {special_state}"
        )
        if self.tank.is_destroyed:
            self.root.setColorScale(0.22, 0.22, 0.22, 1.0)
            self.root.setZ(-0.9)
            self.root.setR(16)
            return

        self.root.setZ(0.0)
        self.root.setR(0)
        self.root.setColorScale(highlight if highlight is not None else Vec4(*self.color))


@dataclass
class Shell:
    node: NodePath
    velocity: Vec3
    owner: str
    damage_kind: str
    source: Tank
    target: Tank | None
    lifetime: float = 0.0


@dataclass
class EnemyBrain:
    tank: Tank
    patrol_heading: float
    team: str
    fire_cooldown: float = 0.0
    special_cooldown: float = 0.0
    scan_timer: float = 0.0
    known_target_pos: Vec3 | None = None
    memory_left: float = 0.0
    last_seen_target_id: int | None = None


@dataclass
class SupportUnit:
    name: str
    team: str
    role: str
    root: NodePath
    label_node: TextNode
    move_speed: float = 0.0
    attack_range: float = INFANTRY_RANGE
    damage_min: int = 1
    damage_max: int = 4
    armor_piercing: int = 0
    preferred_distance: float = 12.0
    fire_cooldown: float = 0.0

    def refresh(self) -> None:
        self.label_node.setText(self.name)


@dataclass
class AirSupport:
    name: str
    team: str
    root: NodePath
    label_node: TextNode
    direction: int
    cooldown: float = AIR_SUPPORT_BASE_COOLDOWN
    active: bool = False
    target_pos: Vec3 | None = None
    strike_done: bool = False

    def refresh(self) -> None:
        self.label_node.setText(self.name)


class TankBattling3D(ShowBase):
    def __init__(self) -> None:
        super().__init__()

        self.disableMouse()
        self.setBackgroundColor(0.56, 0.73, 0.9, 1.0)

        self.player_tank: Tank | None = None
        self.player_view: TankView | None = None
        self.player_team_tanks: list[Tank] = []
        self.player_ai_tanks: list[Tank] = []
        self.enemy_tanks: list[Tank] = []
        self.ai_brains: dict[int, EnemyBrain] = {}
        self.tank_views: dict[int, TankView] = {}
        self.support_units: list[SupportUnit] = []
        self.air_supports: list[AirSupport] = []
        self.shells: list[Shell] = []
        self.player_side = "Allies"
        self.enemy_side = "Axis"
        self.player_spawn_heading = 0.0
        self.player_fire_cooldown = 0.0
        self.player_special_cooldown = 0.0
        self.player_repair_cooldown = 0.0
        self.message_timer = 0.0
        self.match_over = False
        self.game_started = False
        self.keys: dict[str, bool] = {
            "forward": False,
            "backward": False,
            "left": False,
            "right": False,
            "turret_left": False,
            "turret_right": False,
        }

        self.team_colors = {
            "Allies": (0.36, 0.58, 0.35, 1.0),
            "Axis": (0.58, 0.58, 0.62, 1.0),
        }
        self.enemy_team_colors = {
            "Allies": (0.32, 0.5, 0.32, 1.0),
            "Axis": (0.52, 0.52, 0.58, 1.0),
        }
        self.obstacles: list[tuple[Vec3, Vec3]] = []

        self._setup_scene()
        self._setup_ui()
        self._bind_controls()

        self.taskMgr.add(self.update_game, "update-game")
        self.show_start_menu()

    def _setup_scene(self) -> None:
        self.camera.setPos(0, -18, 8)
        self.camera.lookAt(0, 0, 0)

        ambient = AmbientLight("ambient")
        ambient.setColor((0.58, 0.58, 0.6, 1.0))
        self.render.setLight(self.render.attachNewNode(ambient))

        sun = DirectionalLight("sun")
        sun.setColor((0.92, 0.89, 0.82, 1.0))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(-32, -48, 0)
        self.render.setLight(sun_np)

        ground = self.loader.loadModel("models/environment")
        ground.reparentTo(self.render)
        ground.setScale(0.12)
        ground.setPos(-8, 42, -1.2)
        ground.setColorScale(0.62, 0.75, 0.58, 1.0)

        self._build_battlefield()

    def _setup_ui(self) -> None:
        self.title_text = self._create_text("Tank Duel 3D", (-1.28, 0.92), 0.075)
        self.status_text = self._create_text("Choose your tank to begin.", (-1.28, 0.82), 0.05)
        self.controls_text = self._create_text(
            "W/S move  A/D turn  Q/E turret  Space fire  F special  R repair  Tab switch tank",
            (-1.28, 0.74),
            0.043,
        )
        self.hud_text = self._create_text("", (-1.28, 0.64), 0.045)
        self.log_text = self._create_text("Awaiting deployment.", (-1.28, -0.84), 0.05)

        self.panel = DirectFrame(
            frameColor=(0.06, 0.09, 0.12, 0.74),
            frameSize=(-1.34, 1.34, -0.17, 0.17),
            pos=(0, 0, -0.83),
        )

        self.start_frame = DirectFrame(
            frameColor=(0.03, 0.04, 0.05, 0.9),
            frameSize=(-0.98, 0.98, -0.48, 0.48),
            pos=(0, 0, 0.02),
        )
        self._create_text("Choose Your Tank", (-0.38, 0.3), 0.085, parent=self.start_frame)
        self._create_text(
            "Pick your starting tank. You will fight as a full 5-tank team.\nTab switches control between your surviving tanks while aircraft and infantry support both sides.",
            (-0.62, 0.15),
            0.05,
            parent=self.start_frame,
        )

        buttons = [
            ("M4 Sherman", (-0.5, 0, -0.06), self.start_as_sherman),
            ("M3 Grant", (0.0, 0, -0.06), self.start_as_grant),
            ("Panzer IV", (-0.5, 0, -0.26), self.start_as_panzer),
            ("Tiger I", (0.0, 0, -0.26), self.start_as_tiger),
        ]
        self.start_buttons = [
            DirectButton(
                parent=self.start_frame,
                text=label,
                text_scale=0.052,
                scale=0.11,
                frameSize=(-1.8, 1.8, -0.48, 0.8),
                frameColor=(0.18, 0.22, 0.27, 0.94),
                text_fg=(0.96, 0.96, 0.96, 1.0),
                pos=pos,
                command=command,
            )
            for label, pos, command in buttons
        ]

        self.restart_button = DirectButton(
            text="Restart",
            text_scale=0.048,
            scale=0.1,
            frameSize=(-1.5, 1.5, -0.45, 0.72),
            frameColor=(0.2, 0.24, 0.3, 0.94),
            text_fg=(0.96, 0.96, 0.96, 1.0),
            pos=(1.07, 0, 0.91),
            command=self.show_start_menu,
        )
        self.restart_button.hide()

    def _bind_controls(self) -> None:
        self.accept("escape", self.userExit)

        bindings = {
            "w": ("forward", True),
            "w-up": ("forward", False),
            "s": ("backward", True),
            "s-up": ("backward", False),
            "a": ("left", True),
            "a-up": ("left", False),
            "d": ("right", True),
            "d-up": ("right", False),
            "q": ("turret_left", True),
            "q-up": ("turret_left", False),
            "e": ("turret_right", True),
            "e-up": ("turret_right", False),
        }
        for event_name, (key, value) in bindings.items():
            self.accept(event_name, self.set_key, [key, value])

        self.accept("space", self.player_fire)
        self.accept("f", self.player_special)
        self.accept("r", self.player_repair)
        self.accept("tab", self.switch_player_tank)

    def _create_text(
        self,
        text: str,
        pos: tuple[float, float],
        scale: float,
        parent: NodePath | None = None,
    ) -> NodePath:
        node = TextNode("ui-text")
        node.setText(text)
        node.setTextColor(0.96, 0.96, 0.96, 1.0)
        node.setAlign(TextNode.ALeft)
        attach_parent = parent or self.aspect2d
        path = attach_parent.attachNewNode(node)
        path.setScale(scale)
        path.setPos(pos[0], 0, pos[1])
        return path

    def _make_box(
        self,
        parent: NodePath,
        scale: tuple[float, float, float],
        pos: tuple[float, float, float],
        color: tuple[float, float, float, float],
    ) -> NodePath:
        model = self.loader.loadModel("models/misc/rgbCube")
        model.reparentTo(parent)
        model.setScale(*scale)
        model.setPos(*pos)
        model.setColor(*color)
        return model

    def _build_battlefield(self) -> None:
        road = self.loader.loadModel("models/misc/rgbCube")
        road.reparentTo(self.render)
        road.setScale(3.5, 34, 0.05)
        road.setPos(0, 0, -0.95)
        road.setColor(0.4, 0.38, 0.35, 1.0)

        obstacle_specs = [
            ((-14, -7, 0), (3.8, 2.2, 2.1), (0.46, 0.39, 0.29, 1.0)),
            ((12, -2, 0), (4.5, 2.5, 2.4), (0.44, 0.36, 0.26, 1.0)),
            ((-10, 10, 0), (2.7, 4.1, 2.6), (0.43, 0.35, 0.28, 1.0)),
            ((8, 11, 0), (3.0, 3.5, 2.4), (0.42, 0.36, 0.31, 1.0)),
            ((0, 4, 0), (2.4, 2.4, 1.8), (0.5, 0.42, 0.3, 1.0)),
        ]
        for position, scale, color in obstacle_specs:
            block = self._make_box(self.render, scale, position, color)
            block.setZ(scale[2] * 0.5 - 1.0)
            self.obstacles.append(
                (
                    Vec3(position[0], position[1], 0),
                    Vec3(scale[0] * 0.5 + 1.1, scale[1] * 0.5 + 1.1, 0),
                )
            )

        for x_pos in (-24, -18, 18, 24):
            trunk = self._make_box(self.render, (0.8, 0.8, 3.0), (x_pos, 20, 0.4), (0.35, 0.26, 0.18, 1.0))
            trunk.setZ(0.5)
            canopy = self._make_box(self.render, (2.6, 2.6, 1.4), (x_pos, 20, 3.2), (0.18, 0.45, 0.18, 1.0))
            canopy.setH(random.uniform(0, 45))

    def show_start_menu(self) -> None:
        self.start_frame.show()
        self.restart_button.hide()
        self.clear_world()
        self.game_started = False
        self.match_over = False
        self.status_text.node().setText("Choose your tank to begin.")
        self.hud_text.node().setText("")
        self.log("Awaiting deployment.")

    def clear_world(self) -> None:
        for shell in self.shells:
            shell.node.removeNode()
        self.shells.clear()
        for tank_view in self.tank_views.values():
            tank_view.root.removeNode()
        self.tank_views.clear()
        for support_unit in self.support_units:
            support_unit.root.removeNode()
        self.support_units.clear()
        for air_support in self.air_supports:
            air_support.root.removeNode()
        self.air_supports.clear()
        self.ai_brains.clear()
        self.player_tank = None
        self.player_view = None
        self.player_team_tanks.clear()
        self.player_ai_tanks.clear()
        self.enemy_tanks.clear()
        self.player_fire_cooldown = 0.0
        self.player_special_cooldown = 0.0
        self.player_repair_cooldown = 0.0
        for key in self.keys:
            self.keys[key] = False

    def start_as_sherman(self) -> None:
        self.start_match(
            [M4Sherman(), M4Sherman(), M4Sherman(), M3Grant(), M3Grant()],
            [TigerI(), PanzerIV(), PanzerIV(), TigerI(), PanzerIV()],
            "Allies",
            0,
        )

    def start_as_grant(self) -> None:
        self.start_match(
            [M3Grant(), M4Sherman(), M4Sherman(), M3Grant(), M4Sherman()],
            [TigerI(), PanzerIV(), PanzerIV(), TigerI(), PanzerIV()],
            "Allies",
            0,
        )

    def start_as_panzer(self) -> None:
        self.start_match(
            [PanzerIV(), TigerI(), PanzerIV(), TigerI(), PanzerIV()],
            [M4Sherman(), M4Sherman(), M3Grant(), M4Sherman(), M3Grant()],
            "Axis",
            0,
        )

    def start_as_tiger(self) -> None:
        self.start_match(
            [TigerI(), PanzerIV(), PanzerIV(), TigerI(), PanzerIV()],
            [M4Sherman(), M4Sherman(), M3Grant(), M4Sherman(), M3Grant()],
            "Axis",
            0,
        )

    def start_match(self, player_team: list[Tank], enemies: list[Tank], side: str, controlled_index: int) -> None:
        self.clear_world()
        self.start_frame.hide()
        self.restart_button.show()

        self.player_side = side
        self.enemy_side = "Axis" if side == "Allies" else "Allies"
        self.player_team_tanks = player_team
        self.enemy_tanks = enemies
        self.game_started = True
        self.match_over = False
        self.player_spawn_heading = 0 if side == "Allies" else 180
        enemy_side = self.enemy_side

        player_positions = [
            Vec3(-16, -22 if side == "Allies" else 22, 0),
            Vec3(-8, -18 if side == "Allies" else 18, 0),
            Vec3(0, -22 if side == "Allies" else 22, 0),
            Vec3(8, -18 if side == "Allies" else 18, 0),
            Vec3(16, -22 if side == "Allies" else 22, 0),
        ]
        enemy_positions = [
            Vec3(-16, 18 if side == "Allies" else -18, 0),
            Vec3(-8, 22 if side == "Allies" else -22, 0),
            Vec3(0, 18 if side == "Allies" else -18, 0),
            Vec3(8, 22 if side == "Allies" else -22, 0),
            Vec3(16, 18 if side == "Allies" else -18, 0),
        ]

        for tank, position in zip(player_team, player_positions, strict=True):
            self.create_tank_view(
                tank,
                self.team_colors[side],
                position,
                hull_heading=0 if side == "Allies" else 180,
            )

        self.player_tank = player_team[controlled_index]
        self.player_view = self.tank_views[id(self.player_tank)]
        self.player_ai_tanks = [tank for tank in player_team if tank is not self.player_tank]
        for ally_tank in self.player_ai_tanks:
            self.ai_brains[id(ally_tank)] = EnemyBrain(
                tank=ally_tank,
                patrol_heading=0 if side == "Allies" else 180,
                team=side,
            )

        for enemy_tank, position in zip(enemies, enemy_positions, strict=True):
            enemy_view = self.create_tank_view(
                enemy_tank,
                self.enemy_team_colors[enemy_side],
                position,
                hull_heading=180 if side == "Allies" else 0,
            )
            self.ai_brains[id(enemy_tank)] = EnemyBrain(
                tank=enemy_tank,
                patrol_heading=180 if side == "Allies" else 0,
                team=enemy_side,
            )
            enemy_view.turret_pivot.setH(0)

        friendly_backline = -24 if side == "Allies" else 24
        enemy_backline = 24 if side == "Allies" else -24
        self.create_support_unit("Machine Gunners", side, "machine_gunners", Vec3(-24, friendly_backline, 0))
        self.create_support_unit("Gunners", side, "gunners", Vec3(-14, friendly_backline + (2 if side == "Allies" else -2), 0))
        self.create_support_unit("Infantry Squad", side, "riflemen", Vec3(14, friendly_backline + (2 if side == "Allies" else -2), 0))
        self.create_support_unit("Bazooka Team" if side == "Allies" else "Panzerschreck Team", side, "bazooka" if side == "Allies" else "panzerschreck", Vec3(24, friendly_backline, 0))

        self.create_support_unit("Machine Gunners", enemy_side, "machine_gunners", Vec3(-24, enemy_backline, 0))
        self.create_support_unit("Gunners", enemy_side, "gunners", Vec3(-14, enemy_backline + (-2 if side == "Allies" else 2), 0))
        self.create_support_unit("Infantry Squad", enemy_side, "riflemen", Vec3(14, enemy_backline + (-2 if side == "Allies" else 2), 0))
        self.create_support_unit("Bazooka Team" if enemy_side == "Allies" else "Panzerschreck Team", enemy_side, "bazooka" if enemy_side == "Allies" else "panzerschreck", Vec3(24, enemy_backline, 0))
        self.create_air_support("P-47 Thunderbolt", "Allies", 1)
        self.create_air_support("Stuka", "Axis", -1)

        self.camera.setPos(0, -30 if side == "Allies" else 30, 12)
        self.camera.lookAt(self.player_view.root)
        self.log("5 vs 5 battle started. Tanks, infantry, and aircraft are in the fight.")
        self.refresh_hud()

    def create_tank_view(
        self,
        tank: Tank,
        color: tuple[float, float, float, float],
        position: Vec3,
        hull_heading: float,
    ) -> TankView:
        root = self.render.attachNewNode(f"{tank.name}-root")
        root.setPos(position.x, position.y, 0)
        root.setH(hull_heading)

        hull = root.attachNewNode(f"{tank.name}-hull")
        self._make_box(hull, (0.8, 1.55, 0.42), (-0.95, 0, 0.4), (0.1, 0.1, 0.1, 1.0))
        self._make_box(hull, (0.8, 1.55, 0.42), (0.95, 0, 0.4), (0.1, 0.1, 0.1, 1.0))
        self._make_box(hull, (2.2, 3.25, 0.9), (0, 0, 1.06), color)

        turret_pivot = root.attachNewNode(f"{tank.name}-turret")
        turret_pivot.setPos(0, 0.12, 1.9)
        turret_pivot.setH(0)
        self._make_box(turret_pivot, (1.28, 1.4, 0.74), (0, 0, 0), color)
        self._make_box(turret_pivot, (0.2, 2.55, 0.2), (0, 1.95, 0.06), (0.16, 0.16, 0.16, 1.0))
        self._make_box(turret_pivot, (0.26, 0.3, 0.26), (0, 3.35, 0.06), (0.25, 0.25, 0.25, 1.0))

        barrel_tip = turret_pivot.attachNewNode("barrel-tip")
        barrel_tip.setPos(0, 3.45, 0.06)

        label_node = TextNode(f"{tank.name}-label")
        label_node.setAlign(TextNode.ACenter)
        label_node.setTextColor(1.0, 1.0, 1.0, 1.0)
        label_path = root.attachNewNode(label_node)
        label_path.setBillboardAxis()
        label_path.setScale(0.9)
        label_path.setPos(0, 0, 3.4)

        tank_view = TankView(
            tank=tank,
            root=root,
            hull=hull,
            turret_pivot=turret_pivot,
            barrel_tip=barrel_tip,
            label_node=label_node,
            label_path=label_path,
            color=color,
        )
        self.tank_views[id(tank)] = tank_view
        tank_view.refresh()
        return tank_view

    def create_support_unit(self, name: str, team: str, role: str, position: Vec3) -> None:
        color = self.team_colors[team]
        root = self.render.attachNewNode(f"{team}-{role}")
        root.setPos(position)
        self._make_box(root, (1.8, 0.9, 0.5), (0, 0, 0.2), (0.42, 0.34, 0.23, 1.0))
        self._make_box(root, (0.22, 0.22, 0.8), (-0.4, 0.2, 0.8), color)
        self._make_box(root, (0.22, 0.22, 0.8), (0.4, -0.2, 0.8), color)
        move_speed = 2.2
        attack_range = INFANTRY_RANGE
        damage_min = 1
        damage_max = 4
        armor_piercing = 0
        preferred_distance = 12.0
        fire_cooldown = random.uniform(0.6, 2.0)

        if role in {"machine_gunners", "gunners"}:
            self._make_box(root, (0.8, 0.22, 0.16), (0, 0.55, 0.9), (0.15, 0.15, 0.15, 1.0))
            move_speed = 2.8
            attack_range = 20.0
            damage_min = 2
            damage_max = 5
            armor_piercing = 1
            preferred_distance = 14.0
        elif role == "bazooka":
            self._make_box(root, (0.85, 0.18, 0.18), (0.1, 0.45, 0.95), (0.28, 0.25, 0.18, 1.0))
            move_speed = 2.4
            attack_range = 21.0
            damage_min = 10
            damage_max = 16
            armor_piercing = 4
            preferred_distance = 16.0
            fire_cooldown = random.uniform(1.0, 2.5)
        elif role == "panzerschreck":
            self._make_box(root, (0.95, 0.18, 0.2), (0.1, 0.45, 0.95), (0.22, 0.22, 0.2, 1.0))
            move_speed = 2.2
            attack_range = 22.0
            damage_min = 11
            damage_max = 18
            armor_piercing = 5
            preferred_distance = 16.5
            fire_cooldown = random.uniform(1.0, 2.5)
        else:
            self._make_box(root, (0.65, 0.16, 0.12), (0.15, 0.5, 0.85), (0.2, 0.2, 0.2, 1.0))
            move_speed = 2.5
            attack_range = 17.0
            damage_min = 1
            damage_max = 4
            armor_piercing = 0
            preferred_distance = 11.5

        label_node = TextNode(f"{team}-{role}-label")
        label_node.setAlign(TextNode.ACenter)
        label_node.setTextColor(0.95, 0.95, 0.95, 1.0)
        label_path = root.attachNewNode(label_node)
        label_path.setBillboardAxis()
        label_path.setScale(0.8)
        label_path.setPos(0, 0, 2.0)

        support_unit = SupportUnit(
            name=f"{team} {name}",
            team=team,
            role=role,
            root=root,
            label_node=label_node,
            move_speed=move_speed,
            attack_range=attack_range,
            damage_min=damage_min,
            damage_max=damage_max,
            armor_piercing=armor_piercing,
            preferred_distance=preferred_distance,
            fire_cooldown=fire_cooldown,
        )
        support_unit.refresh()
        self.support_units.append(support_unit)

    def create_air_support(self, name: str, team: str, direction: int) -> None:
        root = self.render.attachNewNode(f"{team}-{name}")
        color = self.team_colors[team]
        self._make_box(root, (0.35, 2.2, 0.18), (0, 0, 0), color)
        self._make_box(root, (2.2, 0.35, 0.08), (0, 0, 0), color)
        self._make_box(root, (0.5, 0.5, 0.18), (0, -0.9, 0.12), color)
        label_node = TextNode(f"{team}-{name}-label")
        label_node.setAlign(TextNode.ACenter)
        label_node.setTextColor(1.0, 0.95, 0.82, 1.0)
        label_path = root.attachNewNode(label_node)
        label_path.setBillboardAxis()
        label_path.setScale(0.8)
        label_path.setPos(0, 0, 1.4)

        air_support = AirSupport(
            name=f"{team} {name}",
            team=team,
            root=root,
            label_node=label_node,
            direction=direction,
            cooldown=AIR_SUPPORT_BASE_COOLDOWN + random.uniform(0.0, 4.0),
        )
        air_support.refresh()
        root.hide()
        self.air_supports.append(air_support)

    def set_key(self, key: str, value: bool) -> None:
        self.keys[key] = value

    def switch_player_tank(self) -> None:
        if not self.game_started or self.match_over or not self.player_team_tanks:
            return

        living = [tank for tank in self.player_team_tanks if not tank.is_destroyed]
        if len(living) <= 1:
            return

        if self.player_tank not in living:
            next_tank = living[0]
        else:
            current_index = living.index(self.player_tank)
            next_tank = living[(current_index + 1) % len(living)]

        if self.player_tank is not None and not self.player_tank.is_destroyed:
            self.player_ai_tanks = [tank for tank in self.player_team_tanks if tank is not next_tank]
            if self.player_tank is not next_tank:
                self.ai_brains[id(self.player_tank)] = EnemyBrain(
                    tank=self.player_tank,
                    patrol_heading=self.player_view.root.getH() if self.player_view is not None else self.player_spawn_heading,
                    team=self.player_side,
                )

        self.ai_brains.pop(id(next_tank), None)
        self.player_tank = next_tank
        self.player_view = self.tank_views[id(next_tank)]
        self.player_ai_tanks = [tank for tank in self.player_team_tanks if tank is not next_tank and not tank.is_destroyed]
        self.log(f"Switched control to {next_tank.name}.")
        self.refresh_hud()

    def player_fire(self) -> None:
        if not self.can_player_act() or self.player_fire_cooldown > 0.0:
            return
        assert self.player_tank is not None
        target = self.find_best_target(self.player_tank, self.enemy_tanks, max_range=28.0, forward_required=True)
        self.player_fire_cooldown = PLAYER_FIRE_COOLDOWN
        self.fire_shell(self.player_tank, target, "attack", "player")

    def player_special(self) -> None:
        if not self.can_player_act() or self.player_special_cooldown > 0.0:
            return
        assert self.player_tank is not None
        if not self.player_tank.special_ready:
            self.log("Your special shot has already been used.")
            return
        target = self.find_best_target(self.player_tank, self.enemy_tanks, max_range=30.0, forward_required=True)
        self.player_tank.special_ready = False
        self.player_special_cooldown = PLAYER_SPECIAL_COOLDOWN
        self.fire_shell(self.player_tank, target, "special", "player")

    def player_repair(self) -> None:
        if not self.can_player_act() or self.player_repair_cooldown > 0.0:
            return
        assert self.player_tank is not None
        self.player_repair_cooldown = PLAYER_REPAIR_COOLDOWN
        self.log(self.player_tank.repair())
        self.refresh_hud()

    def can_player_act(self) -> bool:
        return self.game_started and not self.match_over and self.player_tank is not None and not self.player_tank.is_destroyed

    def fire_shell(self, source: Tank, target: Tank | None, damage_kind: str, owner: str) -> None:
        source_view = self.tank_views[id(source)]
        shell_node = self.loader.loadModel("models/misc/sphere")
        shell_node.reparentTo(self.render)
        shell_node.setScale(0.18 if damage_kind == "attack" else 0.24)
        shell_node.setColor(1.0, 0.82 if damage_kind == "attack" else 0.36, 0.15, 1.0)

        origin = source_view.barrel_tip.getPos(self.render)
        direction = source_view.barrel_tip.getQuat(self.render).getForward()
        direction = Vec3(direction.x, direction.y, 0.0)
        if direction.length_squared() <= 0.0001:
            direction = self.forward_from_heading(source_view.turret_pivot.getH(self.render))
        direction.normalize()
        velocity = direction * SHELL_SPEED

        if target is None:
            velocity += Vec3(random.uniform(-2.5, 2.5), random.uniform(-2.5, 2.5), 0.0)

        shell_node.setPos(origin + direction * 0.6)
        self.shells.append(
            Shell(
                node=shell_node,
                velocity=velocity,
                owner=owner,
                damage_kind=damage_kind,
                source=source,
                target=target,
            )
        )

    def update_game(self, task: Task) -> Task:
        dt = globalClock.getDt()
        self.message_timer = max(0.0, self.message_timer - dt)

        if self.game_started and not self.match_over and self.player_view is not None and self.player_tank is not None:
            self.player_fire_cooldown = max(0.0, self.player_fire_cooldown - dt)
            self.player_special_cooldown = max(0.0, self.player_special_cooldown - dt)
            self.player_repair_cooldown = max(0.0, self.player_repair_cooldown - dt)

            self.update_player(dt)
            self.update_ai_team(dt, self.player_ai_tanks, self.enemy_tanks)
            self.update_ai_team(dt, self.enemy_tanks, [tank for tank in self.player_team_tanks if not tank.is_destroyed])
            self.update_support_units(dt)
            self.update_air_supports(dt)
            self.update_shells(dt)
            self.update_camera(dt)
            self.refresh_hud()
            self.check_win_loss()

        return Task.cont

    def update_player(self, dt: float) -> None:
        assert self.player_view is not None and self.player_tank is not None
        move_input = 0.0
        if self.keys["forward"]:
            move_input += 1.0
        if self.keys["backward"]:
            move_input -= 0.7
        turn_input = 0.0
        if self.keys["left"]:
            turn_input += 1.0
        if self.keys["right"]:
            turn_input -= 1.0

        self.player_view.root.setH(self.player_view.root.getH() + turn_input * PLAYER_TURN_SPEED * dt)
        direction = self.player_view.root.getQuat(self.render).getForward()
        direction = Vec3(direction.x, direction.y, 0.0)
        if direction.length_squared() > 0.0:
            direction.normalize()
        current_pos = self.player_view.root.getPos()
        desired = current_pos + direction * move_input * PLAYER_MOVE_SPEED * dt
        self.player_view.root.setPos(self.resolve_movement(current_pos, desired, 1.6))

        turret_turn = 0.0
        if self.keys["turret_left"]:
            turret_turn += 1.0
        if self.keys["turret_right"]:
            turret_turn -= 1.0
        self.player_view.turret_pivot.setH(self.player_view.turret_pivot.getH() + turret_turn * TURRET_TURN_SPEED * dt)

    def update_ai_team(self, dt: float, actors: list[Tank], opponents: list[Tank]) -> None:
        living_opponents = [tank for tank in opponents if not tank.is_destroyed]
        if not living_opponents:
            return

        for actor in actors:
            if actor.is_destroyed:
                continue

            brain = self.ai_brains.get(id(actor))
            if brain is None:
                continue

            view = self.tank_views[id(actor)]
            brain.fire_cooldown = max(0.0, brain.fire_cooldown - dt)
            brain.special_cooldown = max(0.0, brain.special_cooldown - dt)
            brain.scan_timer -= dt

            if brain.scan_timer <= 0.0:
                brain.scan_timer = 0.18 + random.uniform(0.0, 0.18)
                target = self.find_detected_target(actor, living_opponents)
                if target is not None:
                    target_pos = self.tank_views[id(target)].root.getPos()
                    brain.known_target_pos = Vec3(target_pos)
                    brain.last_seen_target_id = id(target)
                    brain.memory_left = MEMORY_TIME
                elif brain.memory_left <= 0.0:
                    brain.known_target_pos = None
                    brain.last_seen_target_id = None

            if brain.memory_left > 0.0:
                brain.memory_left = max(0.0, brain.memory_left - dt)
                if brain.memory_left == 0.0:
                    brain.known_target_pos = None
                    brain.last_seen_target_id = None

            if brain.known_target_pos is None:
                self.enemy_patrol(brain, view, dt)
                continue

            target = self.find_priority_target(actor, living_opponents, brain.last_seen_target_id)
            if target is None:
                continue
            self.enemy_chase_and_fire(brain, view, dt, target)

    def find_detected_target(self, source: Tank, candidates: list[Tank]) -> Tank | None:
        best_target: Tank | None = None
        best_distance = float("inf")
        source_view = self.tank_views[id(source)]
        for candidate in candidates:
            if candidate.is_destroyed:
                continue
            candidate_pos = self.tank_views[id(candidate)].root.getPos()
            if self.enemy_can_detect_position(source_view, candidate_pos):
                distance = (candidate_pos - source_view.root.getPos()).length()
                if distance < best_distance:
                    best_distance = distance
                    best_target = candidate
        return best_target

    def find_closest_target(self, source: Tank, candidates: list[Tank]) -> Tank | None:
        best_target: Tank | None = None
        best_distance = float("inf")
        source_pos = self.tank_views[id(source)].root.getPos()
        for candidate in candidates:
            if candidate.is_destroyed:
                continue
            distance = (self.tank_views[id(candidate)].root.getPos() - source_pos).length()
            if distance < best_distance:
                best_distance = distance
                best_target = candidate
        return best_target

    def find_priority_target(
        self,
        source: Tank,
        candidates: list[Tank],
        preferred_target_id: int | None,
    ) -> Tank | None:
        best_target: Tank | None = None
        best_score = float("inf")
        source_pos = self.tank_views[id(source)].root.getPos()
        for candidate in candidates:
            if candidate.is_destroyed:
                continue
            candidate_view = self.tank_views[id(candidate)]
            distance = (candidate_view.root.getPos() - source_pos).length()
            health_factor = candidate.health / max(1, candidate.max_health)
            preferred_bonus = -6.0 if id(candidate) == preferred_target_id else 0.0
            visible_bonus = -4.0 if not self.line_hits_obstacle(source_pos, candidate_view.root.getPos()) else 0.0
            score = distance + health_factor * 8.0 + preferred_bonus + visible_bonus
            if score < best_score:
                best_score = score
                best_target = candidate
        return best_target

    def get_team_tanks(self, team: str) -> list[Tank]:
        return self.player_team_tanks if team == self.player_side else self.enemy_tanks

    def get_opposing_team_tanks(self, team: str) -> list[Tank]:
        return self.enemy_tanks if team == self.player_side else self.player_team_tanks

    def find_closest_visible_target(self, source_pos: Vec3, candidates: list[Tank], max_range: float) -> Tank | None:
        best_target: Tank | None = None
        best_distance = float("inf")
        for candidate in candidates:
            if candidate.is_destroyed:
                continue
            candidate_pos = self.tank_views[id(candidate)].root.getPos()
            distance = (candidate_pos - source_pos).length()
            if distance > max_range:
                continue
            if self.line_hits_obstacle(source_pos, candidate_pos):
                continue
            if distance < best_distance:
                best_distance = distance
                best_target = candidate
        return best_target

    def find_closest_target_by_team(self, team: str, candidates: list[Tank]) -> Tank | None:
        best_target: Tank | None = None
        best_score = float("inf")
        friendly_tanks = [tank for tank in self.get_team_tanks(team) if not tank.is_destroyed]
        if not friendly_tanks:
            return None
        center = Vec3(0, 0, 0)
        for tank in friendly_tanks:
            center += self.tank_views[id(tank)].root.getPos()
        center /= len(friendly_tanks)

        for candidate in candidates:
            if candidate.is_destroyed:
                continue
            candidate_pos = self.tank_views[id(candidate)].root.getPos()
            score = (candidate_pos - center).length() + candidate.health * 0.04
            if score < best_score:
                best_score = score
                best_target = candidate
        return best_target

    def enemy_can_detect_position(self, enemy_view: TankView, target_pos: Vec3) -> bool:
        offset = target_pos - enemy_view.root.getPos()
        distance = offset.length()
        if distance > DETECTION_RANGE:
            return False
        facing = self.forward_from_heading(enemy_view.root.getH())
        flat_offset = Vec3(offset.x, offset.y, 0.0)
        if flat_offset.length() == 0:
            return True
        flat_offset.normalize()
        dot = max(-1.0, min(1.0, facing.dot(flat_offset)))
        angle = math.degrees(math.acos(dot))
        if angle > DETECTION_FOV:
            return False
        return not self.line_hits_obstacle(enemy_view.root.getPos(), target_pos)

    def enemy_patrol(self, brain: EnemyBrain, view: TankView, dt: float) -> None:
        if random.random() < 0.01:
            brain.patrol_heading += random.uniform(-70, 70)
        self.turn_hull_toward(view, brain.patrol_heading, dt, turn_rate=54.0)
        forward = self.forward_from_heading(view.root.getH())
        next_pos = view.root.getPos() + forward * dt * AI_PATROL_SPEED
        clamped = self.resolve_movement(view.root.getPos(), next_pos, 1.6)
        if (clamped - next_pos).length() > 0.1:
            brain.patrol_heading += random.uniform(90, 180)
        view.root.setPos(clamped)
        self.turn_turret_toward_heading(view, view.root.getH(), dt, turn_rate=74.0)

    def enemy_chase_and_fire(self, brain: EnemyBrain, view: TankView, dt: float, target: Tank) -> None:
        target_pos = self.tank_views[id(target)].root.getPos()
        brain.known_target_pos = Vec3(target_pos)
        brain.last_seen_target_id = id(target)
        to_target = target_pos - view.root.getPos()
        distance = max(0.001, to_target.length())
        desired_heading = math.degrees(math.atan2(to_target.x, to_target.y))

        if distance > 9.0:
            self.turn_hull_toward(view, desired_heading, dt, turn_rate=AI_HULL_TURN_RATE)
            forward = self.forward_from_heading(view.root.getH())
            next_pos = view.root.getPos() + forward * dt * AI_CHASE_SPEED
            view.root.setPos(self.resolve_movement(view.root.getPos(), next_pos, 1.6))
        else:
            self.turn_hull_toward(view, desired_heading + random.uniform(-18, 18), dt, turn_rate=AI_HULL_TURN_RATE * 0.8)

        lead_target = target_pos
        if target is self.player_tank and self.player_view is not None:
            player_forward = self.player_view.root.getQuat(self.render).getForward()
            player_forward = Vec3(player_forward.x, player_forward.y, 0.0)
            if player_forward.length_squared() > 0.0:
                player_forward.normalize()
                lead_target = target_pos + player_forward * 2.4

        self.turn_turret_toward_world(view, lead_target, dt, turn_rate=AI_TURRET_TURN_RATE)

        sight_clear = not self.line_hits_obstacle(view.root.getPos(), target_pos)
        aim_error = abs(self.angle_delta(view.turret_pivot.getH(self.render), desired_heading))
        if sight_clear and distance < 28.0 and aim_error < AI_FIRE_ANGLE_TOLERANCE:
            if brain.special_cooldown <= 0.0 and brain.tank.special_ready and distance < 20.0 and random.random() < AI_SPECIAL_CHANCE:
                brain.tank.special_ready = False
                brain.special_cooldown = ENEMY_SPECIAL_COOLDOWN * 0.8
                self.fire_shell(brain.tank, target, "special", brain.team.lower())
            elif brain.fire_cooldown <= 0.0:
                brain.fire_cooldown = ENEMY_FIRE_COOLDOWN * 0.65 + random.uniform(0.0, 0.25)
                self.fire_shell(brain.tank, target, "attack", brain.team.lower())

    def update_support_units(self, dt: float) -> None:
        for support_unit in self.support_units:
            support_unit.fire_cooldown = max(0.0, support_unit.fire_cooldown - dt)
            targets = self.get_opposing_team_tanks(support_unit.team)
            source_pos = support_unit.root.getPos()
            target = self.find_closest_visible_target(source_pos, targets, support_unit.attack_range + 8.0)
            if target is None:
                self.patrol_support_unit(support_unit, dt)
                continue

            target_pos = self.tank_views[id(target)].root.getPos()
            to_target = target_pos - source_pos
            distance = to_target.length()
            if distance > support_unit.preferred_distance and to_target.length_squared() > 0.001:
                move_dir = Vec3(to_target.x, to_target.y, 0.0)
                move_dir.normalize()
                desired = source_pos + move_dir * support_unit.move_speed * dt
                support_unit.root.setPos(self.resolve_support_movement(source_pos, desired, 0.8))
                source_pos = support_unit.root.getPos()

            if support_unit.fire_cooldown > 0.0:
                continue
            if distance > support_unit.attack_range:
                continue
            if self.line_hits_obstacle(source_pos, target_pos):
                continue

            damage = target.take_damage(
                random.randint(support_unit.damage_min, support_unit.damage_max),
                armor_piercing=support_unit.armor_piercing,
            )
            if support_unit.role in {"machine_gunners", "gunners"}:
                support_unit.fire_cooldown = INFANTRY_FIRE_COOLDOWN
                combat_text = f"{support_unit.name} suppresses {target.name} for {damage} damage."
            elif support_unit.role in {"bazooka", "panzerschreck"}:
                support_unit.fire_cooldown = 3.8
                combat_text = f"{support_unit.name} blasts {target.name} for {damage} damage."
            else:
                support_unit.fire_cooldown = RIFLE_FIRE_COOLDOWN
                combat_text = f"{support_unit.name} chips {target.name} for {damage} damage."

            self.flash_tank(target)
            self.flash_support_fire(support_unit)
            if self.message_timer <= 0.0:
                self.log(combat_text)
                self.message_timer = 0.9

    def patrol_support_unit(self, support_unit: SupportUnit, dt: float) -> None:
        drift = 1.0 if support_unit.team == "Allies" else -1.0
        source_pos = support_unit.root.getPos()
        desired = Vec3(source_pos.x, source_pos.y + drift * support_unit.move_speed * 0.2 * dt, 0.0)
        support_unit.root.setPos(self.resolve_support_movement(source_pos, desired, 0.8))

    def flash_support_fire(self, support_unit: SupportUnit) -> None:
        support_unit.root.setColorScale(1.0, 0.9, 0.55, 1.0)
        self.taskMgr.doMethodLater(
            0.12,
            lambda task, unit=support_unit: self._restore_support_flash(task, unit),
            f"restore-support-{id(support_unit)}",
        )

    def _restore_support_flash(self, task: Task, support_unit: SupportUnit) -> Task:
        support_unit.root.clearColorScale()
        return Task.done

    def update_air_supports(self, dt: float) -> None:
        for air_support in self.air_supports:
            if not air_support.active:
                air_support.cooldown -= dt
                if air_support.cooldown > 0.0:
                    continue

                targets = self.get_opposing_team_tanks(air_support.team)
                target = self.find_closest_target_by_team(air_support.team, targets)
                if target is None:
                    air_support.cooldown = 4.0
                    continue

                target_pos = self.tank_views[id(target)].root.getPos()
                air_support.target_pos = Vec3(target_pos.x, target_pos.y, 0.0)
                start_x = -ARENA_X - 10 if air_support.direction > 0 else ARENA_X + 10
                air_support.root.setPos(start_x, target_pos.y, 18.0)
                air_support.root.setH(90 if air_support.direction > 0 else -90)
                air_support.active = True
                air_support.strike_done = False
                air_support.root.show()
                if self.message_timer <= 0.0:
                    self.log(f"{air_support.name} is making an attack run.")
                    self.message_timer = 1.0
                continue

            air_support.root.setX(air_support.root.getX() + air_support.direction * AIRCRAFT_SPEED * dt)
            if air_support.target_pos is not None and not air_support.strike_done:
                if (air_support.root.getX() - air_support.target_pos.x) * air_support.direction >= 0:
                    self.perform_air_strike(air_support)
                    air_support.strike_done = True

            if abs(air_support.root.getX()) > ARENA_X + 12:
                air_support.active = False
                air_support.cooldown = AIR_SUPPORT_BASE_COOLDOWN + random.uniform(2.0, 6.0)
                air_support.root.hide()

    def perform_air_strike(self, air_support: AirSupport) -> None:
        if air_support.target_pos is None:
            return
        targets = self.get_opposing_team_tanks(air_support.team)
        radius = 5.5 if "P-47" in air_support.name else 4.6
        for target in targets:
            if target.is_destroyed:
                continue
            target_pos = self.tank_views[id(target)].root.getPos()
            if (Vec3(target_pos.x, target_pos.y, 0.0) - air_support.target_pos).length() <= radius:
                if "P-47" in air_support.name:
                    damage = target.take_damage(random.randint(18, 28), armor_piercing=3)
                    message = f"{air_support.name} rockets {target.name} for {damage} damage."
                else:
                    damage = target.take_damage(random.randint(22, 34), armor_piercing=2)
                    message = f"{air_support.name} bombs {target.name} for {damage} damage."
                self.flash_tank(target)
                if self.message_timer <= 0.0:
                    self.log(message)
                    self.message_timer = 1.1

    def update_shells(self, dt: float) -> None:
        remaining: list[Shell] = []
        for shell in self.shells:
            shell.lifetime += dt
            shell.node.setPos(shell.node.getPos() + shell.velocity * dt)

            pos = shell.node.getPos()
            if abs(pos.x) > ARENA_X + 4 or abs(pos.y) > ARENA_Y + 4 or shell.lifetime > 2.4:
                shell.node.removeNode()
                continue

            hit_target = self.find_shell_hit(shell)
            if hit_target is not None:
                self.resolve_shell_hit(shell, hit_target)
                shell.node.removeNode()
                continue

            remaining.append(shell)
        self.shells = remaining

    def find_shell_hit(self, shell: Shell) -> Tank | None:
        if shell.source in self.player_team_tanks:
            candidates = self.enemy_tanks
        else:
            candidates = self.player_team_tanks
        for target in candidates:
            if target is None or target.is_destroyed:
                continue
            view = self.tank_views[id(target)]
            if (shell.node.getPos() - view.root.getPos()).length() < 2.2:
                return target
        return None

    def resolve_shell_hit(self, shell: Shell, target: Tank) -> None:
        if shell.damage_kind == "special":
            message = self.resolve_special_damage(shell.source, target)
        else:
            message = self.resolve_attack_damage(shell.source, target)

        self.flash_tank(target)
        if shell.owner == "player":
            self.log(message)
        elif self.message_timer <= 0.0:
            self.log(f"AI fire: {message}")
        self.message_timer = 1.1

    def resolve_attack_damage(self, source: Tank, target: Tank) -> str:
        raw_damage = random.randint(source.min_damage, source.max_damage)
        damage = target.take_damage(raw_damage)
        return f"{source.name} hits {target.name} for {damage} damage."

    def resolve_special_damage(self, source: Tank, target: Tank) -> str:
        if source.name == "M4 Sherman":
            if random.random() > 0.95:
                return f"{source.name} uses {source.special_name}, but the shot goes wide."
            raw_damage = random.randint(28, 40)
            damage = target.take_damage(raw_damage, armor_piercing=3)
            return f"{source.name} uses {source.special_name} on {target.name} for {damage} damage."
        if source.name == "M3 Grant":
            total_damage = 0
            hits: list[str] = []
            for shot_number in range(1, 3):
                if random.random() <= 0.8:
                    raw_damage = random.randint(14, 22)
                    damage = target.take_damage(raw_damage, armor_piercing=1)
                    total_damage += damage
                    hits.append(f"shot {shot_number} hits for {damage}")
                else:
                    hits.append(f"shot {shot_number} misses")
            return f"{source.name} uses {source.special_name} on {target.name}: {', '.join(hits)}. Total damage: {total_damage}."
        if source.name == "Panzer IV":
            raw_damage = random.randint(26, 36)
            damage = target.take_damage(raw_damage, armor_piercing=4)
            return f"{source.name} uses {source.special_name} on {target.name} for {damage} damage."
        if source.name == "Tiger I":
            if random.random() > 0.85:
                return f"{source.name} unleashes {source.special_name}, but misses."
            raw_damage = random.randint(34, 50)
            damage = target.take_damage(raw_damage, armor_piercing=2)
            return f"{source.name} unleashes {source.special_name} on {target.name} for {damage} damage."
        return source._special_attack(target)

    def flash_tank(self, tank: Tank) -> None:
        view = self.tank_views[id(tank)]
        if tank.is_destroyed:
            view.refresh()
            return
        base_color = Vec4(*view.color)
        view.root.setColorScale(1.0, 0.45, 0.45, 1.0)
        self.taskMgr.doMethodLater(
            0.14,
            lambda task, tank_id=id(tank), color=base_color: self._restore_flash(task, tank_id, color),
            f"restore-flash-{id(tank)}",
        )

    def _restore_flash(self, task: Task, tank_id: int, color: Vec4) -> Task:
        if tank_id in self.tank_views:
            tank = self.tank_views[tank_id].tank
            if not tank.is_destroyed:
                self.tank_views[tank_id].root.setColorScale(color)
        return Task.done

    def update_camera(self, dt: float) -> None:
        assert self.player_view is not None
        root = self.player_view.root
        root_quat = root.getQuat(self.render)
        desired = root.getPos(self.render) + root_quat.xform(Vec3(0, -12, 6.5))
        current = self.camera.getPos()
        self.camera.setPos(current + (desired - current) * min(1.0, dt * 8.0))
        aim_point = root.getPos(self.render) + root_quat.xform(Vec3(0, 7, 2.2))
        self.camera.lookAt(aim_point)

    def refresh_hud(self) -> None:
        if self.player_tank is None:
            self.hud_text.node().setText("")
            return

        enemies_left = sum(not tank.is_destroyed for tank in self.enemy_tanks)
        allies_left = sum(not tank.is_destroyed for tank in self.player_team_tanks)
        air_ready = sum(1 for air in self.air_supports if air.team == self.player_side and not air.active and air.cooldown <= 3.0)
        self.status_text.node().setText(
            "Destroy all enemy tanks. Stay out of their view cone to break contact."
            if not self.match_over
            else self.status_text.node().getText()
        )
        self.hud_text.node().setText(
            f"{self.player_tank.name} HP {self.player_tank.health}/{self.player_tank.max_health}"
            f" | Allies Left {allies_left}"
            f" | Enemies Left {enemies_left}"
            f" | Air Support {'Ready' if air_ready else 'Reloading'}"
            f" | Fire {self.cooldown_text(self.player_fire_cooldown)}"
            f" | Special {'Ready' if self.player_tank.special_ready and self.player_special_cooldown <= 0 else f'{self.player_special_cooldown:.1f}s'}"
            f" | Repair {self.cooldown_text(self.player_repair_cooldown)}"
        )

        for tank_view in self.tank_views.values():
            highlight = None
            if tank_view.tank == self.player_tank and not tank_view.tank.is_destroyed:
                highlight = Vec4(0.7, 0.88, 0.7, 1.0)
            elif tank_view.tank in self.player_team_tanks and not tank_view.tank.is_destroyed:
                highlight = Vec4(0.55, 0.72, 0.9, 1.0)
            tank_view.refresh(highlight)

    def cooldown_text(self, cooldown: float) -> str:
        return "Ready" if cooldown <= 0.0 else f"{cooldown:.1f}s"

    def check_win_loss(self) -> None:
        if self.match_over:
            return
        if all(tank.is_destroyed for tank in self.player_team_tanks):
            self.match_over = True
            self.status_text.node().setText("Defeat. Your team was wiped out.")
            self.log("All of your tanks have been destroyed.")
            return
        if all(enemy.is_destroyed for enemy in self.enemy_tanks):
            self.match_over = True
            self.status_text.node().setText("Victory. Your team beat the computer.")
            self.log("All enemy tanks are burning wrecks.")
            return

        if self.player_tank is not None and self.player_tank.is_destroyed:
            self.switch_player_tank()

    def log(self, message: str) -> None:
        self.log_text.node().setText(message)

    def resolve_movement(self, current: Vec3, proposed: Vec3, radius: float) -> Vec3:
        clamped = self.clamp_to_arena(proposed)
        if not self.position_hits_obstacle(clamped, radius):
            return clamped
        return self.clamp_to_arena(current)

    def resolve_support_movement(self, current: Vec3, proposed: Vec3, radius: float) -> Vec3:
        clamped = self.clamp_to_arena(proposed)
        if not self.position_hits_obstacle(clamped, radius):
            return clamped
        slide_x = self.clamp_to_arena(Vec3(clamped.x, current.y, 0.0))
        if not self.position_hits_obstacle(slide_x, radius):
            return slide_x
        slide_y = self.clamp_to_arena(Vec3(current.x, clamped.y, 0.0))
        if not self.position_hits_obstacle(slide_y, radius):
            return slide_y
        return self.clamp_to_arena(current)

    def clamp_to_arena(self, position: Vec3) -> Vec3:
        return Vec3(
            max(-ARENA_X, min(ARENA_X, position.x)),
            max(-ARENA_Y, min(ARENA_Y, position.y)),
            0.0,
        )

    def position_hits_obstacle(self, position: Vec3, radius: float) -> bool:
        for obstacle_pos, obstacle_half in self.obstacles:
            if (
                abs(position.x - obstacle_pos.x) < obstacle_half.x + radius
                and abs(position.y - obstacle_pos.y) < obstacle_half.y + radius
            ):
                return True
        return False

    def line_hits_obstacle(self, start: Vec3, end: Vec3) -> bool:
        direction = end - start
        distance = direction.length()
        if distance <= 0.001:
            return False
        steps = max(2, int(distance / 1.2))
        for step in range(1, steps):
            sample = start + direction * (step / steps)
            for obstacle_pos, obstacle_half in self.obstacles:
                if (
                    abs(sample.x - obstacle_pos.x) <= obstacle_half.x
                    and abs(sample.y - obstacle_pos.y) <= obstacle_half.y
                ):
                    return True
        return False

    def forward_from_heading(self, heading: float) -> Vec3:
        radians = math.radians(heading)
        return Vec3(math.sin(radians), math.cos(radians), 0.0)

    def angle_delta(self, current: float, target: float) -> float:
        return ((target - current + 180.0) % 360.0) - 180.0

    def turn_hull_toward(self, view: TankView, target_heading: float, dt: float, turn_rate: float) -> None:
        current = view.root.getH()
        delta = self.angle_delta(current, target_heading)
        step = max(-turn_rate * dt, min(turn_rate * dt, delta))
        view.root.setH(current + step)

    def turn_turret_toward_world(self, view: TankView, world_pos: Vec3, dt: float, turn_rate: float) -> None:
        offset = world_pos - view.root.getPos()
        target_heading = math.degrees(math.atan2(offset.x, offset.y))
        current = view.turret_pivot.getH(self.render)
        delta = self.angle_delta(current, target_heading)
        step = max(-turn_rate * dt, min(turn_rate * dt, delta))
        view.turret_pivot.setH(self.render, current + step)

    def turn_turret_toward_heading(self, view: TankView, target_heading: float, dt: float, turn_rate: float) -> None:
        current = view.turret_pivot.getH(self.render)
        delta = self.angle_delta(current, target_heading)
        step = max(-turn_rate * dt, min(turn_rate * dt, delta))
        view.turret_pivot.setH(self.render, current + step)

    def find_best_target(
        self,
        source: Tank,
        candidates: list[Tank],
        max_range: float,
        forward_required: bool,
    ) -> Tank | None:
        source_view = self.tank_views[id(source)]
        origin = source_view.root.getPos()
        turret_heading = source_view.turret_pivot.getH(self.render)
        facing = self.forward_from_heading(turret_heading)

        best_score = float("inf")
        best_target: Tank | None = None
        for candidate in candidates:
            if candidate.is_destroyed:
                continue
            candidate_view = self.tank_views[id(candidate)]
            offset = candidate_view.root.getPos() - origin
            distance = offset.length()
            if distance > max_range:
                continue
            if self.line_hits_obstacle(origin, candidate_view.root.getPos()):
                continue
            direction = Vec3(offset.x, offset.y, 0.0)
            if direction.length() == 0:
                continue
            direction.normalize()
            angle = math.degrees(math.acos(max(-1.0, min(1.0, facing.dot(direction)))))
            if forward_required and angle > 20.0:
                continue
            score = distance + angle * 0.35
            if score < best_score:
                best_score = score
                best_target = candidate
        return best_target


if __name__ == "__main__":
    app = TankBattling3D()
    app.run()
