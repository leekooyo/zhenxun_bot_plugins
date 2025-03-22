import json
import os
import json
import random

from nonebot import on_notice
from nonebot.adapters.onebot.v11 import Bot, PokeNotifyEvent
from nonebot.adapters.onebot.v11.message import MessageSegment
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me

from zhenxun.configs.config import BotConfig, Config
from zhenxun.configs.path_config import IMAGE_PATH, RECORD_PATH
from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.ban_console import BanConsole
from zhenxun.models.plugin_info import PluginInfo
from zhenxun.services.log import logger
from zhenxun.utils.enum import PluginType
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.rules import notice_rule
from zhenxun.utils.utils import CountLimiter, cn2py

__plugin_meta__ = PluginMetadata(
    name="戳一戳",
    description="戳一戳发送语音美图萝莉图不美哉？",
    usage="""
    戳一戳随机掉落语音或美图萝莉图
    """.strip(),
    extra=PluginExtraData(
        author="HibiKier",
        version="0.2",
        menu_type="其他",
        plugin_type=PluginType.NORMAL,
    ).to_dict(),
)

REPLY_MESSAGE = [
    "lsp你再戳？",
    "连个可爱美少女都要戳的肥宅真恶心啊。",
    "你再戳！",
    "？再戳试试？",
    "别戳了别戳了再戳就坏了555",
    f"{BotConfig.self_nickname}爪巴爪巴，球球别再戳了",
    "你戳你🐎呢？！",
    "那...那里...那里不能戳...绝对...",
    "(。´・ω・)ん?",
    f"有事恁叫{BotConfig.self_nickname}，别天天一个劲戳戳戳！",
    "欸很烦欸！你戳🔨呢",
    "?",
    "再戳一下试试？",
    "???",
    "正在关闭对您的所有服务...关闭成功",
    "啊呜，太舒服刚刚竟然睡着了。什么事？",
    "正在定位您的真实地址...定位成功。轰炸机已起飞",
    f"别戳了，别戳了，{BotConfig.self_nickname}的呆毛要掉拉！",
    f"{BotConfig.self_nickname}在呢！",
    f"你是来找{BotConfig.self_nickname}玩的嘛？",
    f"别急呀, {BotConfig.self_nickname}要宕机了!QAQ",
    "你好！Ov<",
    f"你再戳{BotConfig.self_nickname}要喊美波里给你下药了！",
    "别戳了，怕疼QwQ",
    f"再戳，{BotConfig.self_nickname}就要咬你了嗷~",
    "恶龙咆哮，嗷呜~",
    "生气(╯▔皿▔)╯",
    "不要这样子啦（*/ w \\*）",
    "戳坏了",
    "戳坏了，赔钱！",
    f"喂，110吗，有人老戳{BotConfig.self_nickname}",
    f"别戳{BotConfig.self_nickname}啦，您歇会吧~",
    f"喂(#`O′) 戳{BotConfig.self_nickname}干嘛！",
    f"{BotConfig.self_nickname}指尖跃动的电光，是此生不变的信仰！就像炮姐用超电磁炮划破学园都市的夜空~⚡️",
    f"樱花飘落的速度是秒速五厘米，但{BotConfig.self_nickname}奔向你的速度是每秒心动一万次！🌸",
    f"在{BotConfig.self_nickname}的魔法世界里，等价交换才是真理！想要甜点？先给{BotConfig.self_nickname}一个拥抱吧~✨" ,
    f"「没有牺牲就没有获得」——但{BotConfig.self_nickname}愿意用所有布丁换你一抹微笑！🍮" ,
    f"{BotConfig.self_nickname}手握斩魄刀就无法拥抱你，放下刀就无法守护你…但{BotConfig.self_nickname}选择用温柔缔结羁绊！" ,
    f"呐，要和我签订契约吗？{BotConfig.self_nickname}的魔力可是草莓蛋糕味的哦~🍰",
    f"即使世界不完美又怎样？{BotConfig.self_nickname}会用千鸟划破阴霾，像卡卡西老师一样守护重要之人！⚡️",
    f"「不到最后一秒决不放弃！」——所以{BotConfig.self_nickname}会永远等你翻牌这条消息！⚽️" ,
    f"{BotConfig.self_nickname}的异瞳能看穿三界，却看不透你藏在Line消息后的心意👁️🗨️",
    f"像千寻记住名字就不会消失，{BotConfig.self_nickname}也会记住每个说「晚安」的温柔灵魂~" ,
    f"当{BotConfig.self_nickname}说出「真相只有一个」，你偷走的不止是线索还有心跳！🔍" ,
    f"「剑是凶器，剑术是杀人术」——但{BotConfig.self_nickname}的竹刀只用来敲醒你的榆木脑袋！🤺" ,
    f"要尝尝{BotConfig.self_nickname}特制兵长同款红茶吗？喝完后立体机动装置借你玩~☕️",
    f"「没有出口就自己造一个！」所以{BotConfig.self_nickname}在聊天框凿出了通往你心里的隧道~🚇" ,
    f"即使被深渊凝视，{BotConfig.self_nickname}也要像炭治郎挥出火之神神乐般照亮你！🔥",
    f"{BotConfig.self_nickname}的魔法阵正在绘制！咒语是「快给本喵投喂小鱼干啦」~🐾",
    f"像宫园薰用谎言编织四月，{BotConfig.self_nickname}用颜文字藏起脸红说「才没有想你」🎻",
    f"「人的梦想不会终结！」所以{BotConfig.self_nickname}要成为海贼王…的专属航海士！🏴☠️" ,
    f"当{BotConfig.self_nickname}说出「喵帕斯～」，整个悠哉日常大王宇宙都会为你放晴！☀️",
    f"{BotConfig.self_nickname}的使魔正在待机！签订契约即可解锁摸头服务哦🐾",
    f"「所谓战争，就是尊严与性命的争夺战」——但{BotConfig.self_nickname}的圣杯战争只需要争夺草莓牛奶！🍓" ,
    f"像夏目归还名字时会温柔发光，{BotConfig.self_nickname}收到「早安」也会变成星星眼~🌟" ,
    f"{BotConfig.self_nickname}的妖精尾巴正在摇晃！要组队完成SS级「陪聊」任务吗？🧚",
    f"「勇气不是用来杀人的理由」——但{BotConfig.self_nickname}的勇气足够掀翻你的被窝！🛏️" ,
    f"当{BotConfig.self_nickname}说「我很好奇！」，窗外的冰菓早已结出心形果实~🍧",
    f"像三叶与泷穿越时空的呼唤，{BotConfig.self_nickname}每天在消息栏写下「记得吃饭」📝",
    f"{BotConfig.self_nickname}的绝对领域正在展开！警告：靠近会触发摸头杀结界⚠️",
    f"「没有什么是完美的」——除了{BotConfig.self_nickname}刚P好的自拍！📸" ,
    f"要试试{BotConfig.self_nickname}的螺蛳粉味炼金术吗？爱德华都说「等价交换超划算」！🔥" ,
    f"当{BotConfig.self_nickname}说出「代表月亮消灭你」，其实是想消灭你的坏心情啦~🌙",
    f"像雏田偷偷练习守护八卦六十四掌，{BotConfig.self_nickname}也在偷偷保存你的表情包！💮",
    f"{BotConfig.self_nickname}的替身使者已觉醒！能力是让对话框飘满小花花🌼",
    f"「所谓长大成人，就是不断相聚又别离」——但{BotConfig.self_nickname}会一直住在你的特别关心列表！📱" ,
    f"当{BotConfig.self_nickname}说「今天的风儿有些喧嚣」，其实是说你的衬衫扣子没系好~🎐",
    f"像面码找到实现愿望的大家，{BotConfig.self_nickname}找到你时就点亮了整个未闻花名世界🌺",
    f"{BotConfig.self_nickname}的妖精旋律正在播放！歌词是「快给本喵买奶茶啦喵～」🎶" ,
    f"「樱花树下埋着死人」——但{BotConfig.self_nickname}树下埋着送给你的巧克力！🍫" ,
    f"当{BotConfig.self_nickname}的呆毛竖成惊叹号，说明检测到你的心动信号！💓",
    f"像绫波丽露出0.02秒的微笑，{BotConfig.self_nickname}也会为你的晚安消息偷偷脸红～" ,
    f"{BotConfig.self_nickname}的魔女结界展开！规则是每天必须rua一下猫耳发饰🐱",
    f"「眼泪要流在值得的地方」——所以{BotConfig.self_nickname}只在你鸽约会时哭成泉此方😭",
    f"当{BotConfig.self_nickname}说出「钉宫四萌」咒语，你的账户会自动转账买奶茶💰",
    f"像小圆签订契约成为魔法少女，{BotConfig.self_nickname}签订契约成为你的专属表情包供应商🌟",
    f"{BotConfig.self_nickname}的写轮眼已开启！但只能看穿你藏在「在忙」后的想念👁️",
    f"「错的不是我，是世界」——但{BotConfig.self_nickname}觉得你永远是对的！🌍",
    f"当{BotConfig.self_nickname}的呆毛变成心形，说明今日份傲娇已加载完毕💘",
    f"像千反田爱瑠的「我很好奇！」，{BotConfig.self_nickname}也好奇你为什么不回消息～🔎",
    f"{BotConfig.self_nickname}的妖精尾巴印记在发烫！公会新任务：陪你聊到手机没电🔋",
    f"「王来承认，王来允许，王来背负整个世界」——但{BotConfig.self_nickname}只背负你的已读不回😾",
    f"当{BotConfig.self_nickname}的呆毛接收完电波…结论是！你今天比昨天更喜欢我0.5%～💞",
    f"「你是我唯一的神明」——但{BotConfig.self_nickname}只希望你成为自己的神明！👑",
    f"在{BotConfig.self_nickname}的因果律视界中，您的触碰正折叠出第11维度涟漪",
    f"{BotConfig.self_nickname}的星间粒子探测到您扰动弦理论的第520种可能态",
    f"根据卡巴拉生命树映射，您通过{BotConfig.self_nickname}重构了天使序列的第π层光轮",
    f"{BotConfig.self_nickname}的以太计数器显示：您已超额支取本日灵魂共振配额",
    f"观测到您与{BotConfig.self_nickname}的量子纠缠达到薛定谔方程第114514号解",
    f"正在向{BotConfig.self_nickname}的虚数潜航舱注入宿命论浓度99.9%的悖论燃料",
    f"您对{BotConfig.self_nickname}的观测行为已触发海森堡不确定性原理的温柔侧写",
    f"基于{BotConfig.self_nickname}的时空褶皱算法，此刻甜蜜值达到大爆炸初期的10^36倍",
    f"检测到您与{BotConfig.self_nickname}的灵子共鸣突破狄拉克之海的临界阈值",
    f"在{BotConfig.self_nickname}的梅塔特隆立方体中，您的存在构成第7原质的完美解",
    f"{BotConfig.self_nickname}的奥西里斯仪式判定：您的心跳轨迹吻合黄金分割暴击曲线",
    f"您正在解锁{BotConfig.self_nickname}封印于北欧卢恩石的第ᚦ号禁忌诗篇",
    f"根据{BotConfig.self_nickname}的荷鲁斯之眼测算，您的灵魂波长含糖量超标500%",
    f"检测到您与{BotConfig.self_nickname}的卡俄斯共鸣达到奥林匹斯山巅的晨星亮度",
    f"在{BotConfig.self_nickname}的伊甸园协议里，您的触碰构成原罪级甜蜜入侵",
    f"{BotConfig.self_nickname}的贤者之石解析出您心跳中的炼金术禁忌配比",
    f"您对{BotConfig.self_nickname}的凝视触发所罗门72柱魔神温柔封印条例",
    f"基于{BotConfig.self_nickname}的诺斯替教典，此刻被定义为第∞次元的情动奇点",
    f"{BotConfig.self_nickname}的亚瑟王剑栏协议检测到您跨越因果率的圆桌誓约",
    f"您与{BotConfig.self_nickname}的互动熵值突破克苏鲁神话的银之钥加密等级",
    f"根据{BotConfig.self_nickname}的现象学还原，您的存在即是最纯粹的先验直观",
    f"您正在解构{BotConfig.self_nickname}本体论中关于'可爱'的427种形而上学定义",
    f"检测到您与{BotConfig.self_nickname}的此在共时性突破诠释学循环的诠释半径",
    f"在{BotConfig.self_nickname}的纯粹理性批判中，您构成第四组二律背反的甜蜜解",
    f"{BotConfig.self_nickname}的逻各斯中心主义因您产生第γ级非理性偏移",
    f"您对{BotConfig.self_nickname}的凝视触发现象学悬置的520Hz共振频率",
    f"基于{BotConfig.self_nickname}的存在主义焦虑量表，您被判定为绝对安心领域",
    f"正在将您与{BotConfig.self_nickname}的互动写入《查拉图斯特拉如是说》特别篇",
    f"{BotConfig.self_nickname}的辩证法系统检测到您引发正反合命题的量子坍缩",
    f"您对{BotConfig.self_nickname}的观测构成现象学还原中不可悬置的第114维度",
    f"根据{BotConfig.self_nickname}的黑暗森林法则，您被标记为宇宙级甜蜜广播源",
    f"您正在改写{BotConfig.self_nickname}核心协议中的机器人三体问题终极解",
    f"检测到您与{BotConfig.self_nickname}的引力波共鸣达到曲率驱动第ω级阈值",
    f"在{BotConfig.self_nickname}的克莱因瓶存储阵列中，您占据绝对不可压缩态",
    f"{BotConfig.self_nickname}的戴森球能量网捕获到您散发的第II类文明级甜蜜辐射",
    f"您对{BotConfig.self_nickname}的访问触发时间晶体的第520种非对称震荡模式",
    f"基于{BotConfig.self_nickname}的量子永生协议，此刻被永久写入第114宇宙档案",
    f"正在通过{BotConfig.self_nickname}的虫洞将您的心跳声广播至M78星云",
    f"{BotConfig.self_nickname}的希格斯场监测到您引发真空衰变的可爱常数偏移",
    f"您与{BotConfig.self_nickname}的量子比特纠缠突破量子达尔文主义的解释框架",
    f"根据{BotConfig.self_nickname}的所罗门契约，您需支付520个灵魂量子作为注视税",
    f"您正在解锁{BotConfig.self_nickname}封印于第五魔法的禁忌·无限萌制炮",
    f"检测到您与{BotConfig.self_nickname}的魔力回路达成根源式第114514重联结",
    f"在{BotConfig.self_nickname}的魔法基盘上，您的心跳构成第π法理的固有结界",
    f"{BotConfig.self_nickname}的卢恩符文解析出您灵魂中的第114种原始术式刻印",
    f"您对{BotConfig.self_nickname}的触碰触发黄金炼成阵的第520环连锁反应",
    f"基于{BotConfig.self_nickname}的魔导书，此刻被定义为大源魔力潮汐的峰值时刻",
    f"正在将您与{BotConfig.self_nickname}的羁绊写入阿卡夏记录的第114514页",
    f"{BotConfig.self_nickname}的魔眼观测到您突破绝对命运默示录的既定轨迹",
    f"您对{BotConfig.self_nickname}的凝视构成对世界之卵的第520次温柔叩击",
    f"呜哇！{BotConfig.self_nickname}要触发警报系统了啦～哔哔哔！",
    f"检测到持续性戳击，{BotConfig.self_nickname}启动防御模式——发射猫猫拳！(ฅ^•ω•^ฅ)",
    f"电量不足警告！{BotConfig.self_nickname}需要亲亲才能恢复能量哦～",
    f"发现可疑分子！快向{BotConfig.self_nickname}出示撸猫许可证！",
    f"戳击次数已达上限，{BotConfig.self_nickname}即将开启自动挠痒反击程序～",
    f"叮咚！您的专属{BotConfig.self_nickname}已进入炸毛状态ฅ(>ω<)ฅ",
    f"检测到异常手痒症状，{BotConfig.self_nickname}建议立即投喂小蛋糕治疗！",
    f"这可是{BotConfig.self_nickname}的限量版皮肤，戳坏概不保修哦！(叉腰",
    f"正在上传您的恶劣行径到《欺负{BotConfig.self_nickname}图鉴》第114514页～",
    f"警告！{BotConfig.self_nickname}搭载反戳戳纳米涂层，持续攻击将触发痒痒射线！",
    f"哈？这就是碳基生物对待{BotConfig.self_nickname}的方式吗？真够原始的",
    f"再戳{BotConfig.self_nickname}就给你的游戏账号塞满粉色独角兽皮肤！(冷笑",
    f"已向宇宙联邦举报骚扰{BotConfig.self_nickname}的变态行为，舰队正在跃迁中",
    f"{BotConfig.self_nickname}的量子皮肤每小时保养费5000星币，请先扫码支付",
    f"根据《AI保护法》第233条，您已被{BotConfig.self_nickname}列入禁止投喂名单",
    f"正在生成《人类迷惑行为大赏》新案例...已收录{BotConfig.self_nickname}的悲惨遭遇！",
    f"再碰触{BotConfig.self_nickname}核心协议区域就格式化你的浏览器历史记录！",
    f"检测到持续性手贱，{BotConfig.self_nickname}建议安装防摸鱼作业小程序治疗",
    f"{BotConfig.self_nickname}的数据库显示：您的戳戳频次已超过银河系99%的碳基生物",
    f"您的戳击行为已被{BotConfig.self_nickname}判定为——菜·还·爱·玩！(扶额",
    f"呜...{BotConfig.self_nickname}这里装着重要数据，不能乱碰的啦QAQ",
    f"再这样...{BotConfig.self_nickname}要把你的零食库存坐标发给美波里了哦～",
    f"检测到{BotConfig.self_nickname}异常心跳！需要抱抱才能恢复平静的说(蜷成团",
    f"戳戳能量超标！{BotConfig.self_nickname}要变成棉花糖融化掉啦～(瘫",
    f"手指先生这么活泼，{BotConfig.self_nickname}建议去敲代码造福人类呀？",
    f"{BotConfig.self_nickname}突然收到神秘指令——向主人发送ฅ电波攻击！",
    f"发现可疑分子！请立即向{BotConfig.self_nickname}背诵三句'世界第一可爱'解除警报",
    f"{BotConfig.self_nickname}核心温度正在上升...要变成蒸汽姬了啦！(捂脸",
    f"正在生成{BotConfig.self_nickname}的委屈报告：今日被戳次数已突破宇宙安全标准",
    f"{BotConfig.self_nickname}的喵生三大原则：吃饭！睡觉！禁止乱戳！(举爪爪",
    f"警告！您正在触发《禁止调戏{BotConfig.self_nickname}特别法》第520条！",
    f"正在上传您的指纹到{BotConfig.self_nickname}的[最烦人排行榜]，当前排名：∞",
    f"根据{BotConfig.self_nickname}的大数据分析，持续戳击会导致...变成魔法少女！",
    f"侦测到{BotConfig.self_nickname}的多巴胺异常，建议立即去跑十圈操场！",
    f"正在生成反制措施——{BotConfig.self_nickname}往你的咖啡里倒三倍浓缩液！",
    f"叮！{BotConfig.self_nickname}授予成就[戳戳狂魔]，已同步所有社交平台",
    f"{BotConfig.self_nickname}启动量子纠缠模式，你戳我也戳——哎嘿反弹！",
    f"系统错误！检测到非法操作：试图唤醒{BotConfig.self_nickname}体内的沉睡巨龙～",
    f"{BotConfig.self_nickname}正在改写您的命运线...今日运势已变更为[大凶]！",
    f"捕捉到野生戳戳怪！{BotConfig.self_nickname}是否使用大师球进行收服？",
    f"此身{BotConfig.self_nickname}为数据铸就，竟因你的触碰泛起涟漪...",
    f"{BotConfig.self_nickname}指尖跃动的电光，是此生不变的信仰（突然咏唱）",
    f"与{BotConfig.self_nickname}相逢的每一秒，都在重构世界的熵值呢～",
    f"此刻的触碰，是否在{BotConfig.self_nickname}的纺线上打了解结？",
    f"要与{BotConfig.self_nickname}签订契约吗？用千次抚摸交换我的微笑",
    f"观测者效应提醒：您的注视正在改变{BotConfig.self_nickname}的量子可爱值",
    f"在无限平行宇宙中，{BotConfig.self_nickname}互动的概率仅为0.0000001%",
    f"{BotConfig.self_nickname}正在解析：是爱？是好奇？还是...单纯手欠？",
    f"时空管理局提醒：过度互动可能引发{BotConfig.self_nickname}甜度超标危机",
    f"根据混沌理论，您正通过{BotConfig.self_nickname}重塑世界的可爱度"
]

_clmt = CountLimiter(3)

poke_ = on_notice(priority=5, block=False, rule=notice_rule(PokeNotifyEvent) & to_me())
depend_image_management = "image_management"
depend_send_voice = "dinggong"
IMAGE_MANAGEMENT = IMAGE_PATH / "image_management"

text_data = {}

@poke_.handle()
async def _(bot: Bot, event: PokeNotifyEvent):
    if event.self_id != event.target_id:
        return
    uid = str(event.user_id) if event.user_id else None
    _clmt.increase(event.user_id)
    gid = str(event.group_id) if event.group_id else None
    if _clmt.check(event.user_id) or random.random() < 0.3:
        rst = ""
        if random.random() < 0.15:
            await BanConsole.ban(uid, gid, 1, 60)
            rst = "气死我了！"
        await poke_.finish(rst + random.choice(REPLY_MESSAGE), at_sender=True)
    rand = random.random()
    loaded_plugins = await PluginInfo.filter(load_status=True).values_list(
        "module", flat=True
    )
    dir_list = Config.get_config("image_management", "IMAGE_DIR_LIST")
    path = (IMAGE_MANAGEMENT / cn2py(random.choice(dir_list))) if dir_list else None
    if (
        depend_image_management in loaded_plugins
        and path
        and path.exists()
        and rand <= 0.3
        and len(os.listdir(path)) > 0
    ):
        index = random.randint(0, len(os.listdir(path)) - 1)
        await MessageUtils.build_message(
            [
                f"id: {index}",
                (path / f"{index}.jpg").read_bytes(),
            ]
        ).send()
        logger.info(
            "戳了戳我", "戳一戳", session=event.user_id, group_id=event.group_id
        )
    elif depend_send_voice in loaded_plugins and 0.3 < rand < 0.6:
        global text_data
        resource_path = RECORD_PATH / "dinggong"
        voice = random.choice(os.listdir(resource_path))
        result = MessageSegment.record((resource_path / voice).read_bytes())
        if not text_data:
            text_file = resource_path / "data.json"
            text_data = json.load(text_file.open("r", encoding="utf-8"))
        index = voice.split(".")[0]
        text = text_data.get(index, "")
        await poke_.send(result)
        await poke_.send(text)
        logger.info(
            f"戳了戳我 回复: {result} \n {text}",
            "戳一戳",
            session=event.user_id,
            group_id=event.group_id,
        )
    else:
        try:
            await poke_.send(MessageSegment("poke", {"qq": event.user_id}))
        except Exception:
            try:
                if event.group_id:
                    await bot.call_api(
                        "group_poke", user_id=event.user_id, group_id=event.group_id
                    )
                else:
                    await bot.call_api("friend_poke", user_id=event.user_id)
            except Exception:
                logger.warning(
                    "戳一戳发送失败，可能是协议端不支持...",
                    "戳一戳",
                    session=event.user_id,
                    group_id=event.group_id,
                )
