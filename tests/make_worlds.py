#!/usr/bin/env python3
"""把魔戒/冰火测试数据转成 WGP v0.4 条目仓库（中土 + 维斯特洛）。"""
import shutil
from pathlib import Path

ROOT = Path(__file__).parent


def fm(id, title, type_, status, layer=None, load_bearing=False,
       canon_refs="[]", conflicts="[]", depends="[]", superseded="null",
       owns="[]", legitimacy="", member_of="[]"):
    lb = "true" if load_bearing else "false"
    layer_line = f"layer: {layer}\n" if layer else ""
    owns_line = f"owns: {owns}\n" if owns != "[]" else ""
    member_line = f"member_of: {member_of}\n" if member_of != "[]" else ""
    # kind=legitimacy 的依赖走拆分后的关系名 derives_legitimacy_from（无 kind 行）；
    # 全部依赖都是 legitimacy 时 depends_on 行整行消失（与已提交的世界字节一致）
    depends_line = f"depends_on: {depends}\n" if depends is not None else ""
    legit_line = f"derives_legitimacy_from:{legitimacy}\n" if legitimacy else ""
    return f"""---
id: {id}
title: {title}
type: {type_}
author: dataset-v1
date: 2026-09-23
status: {status}
load_bearing: {lb}
{layer_line}{owns_line}{member_line}canon_refs: {canon_refs}
conflicts_with: {conflicts}
{depends_line}{legit_line}superseded_by: {superseded}
ai_assisted: false
---
"""


def evm(id, kind, when, when_sort, body, legs="", status="canon"):
    """流水事件卡（协议 1.2）。legs 是 by/to/object 的 YAML 片段；
    body 必填且 ≥200 字（canon 事件卡同样受 CA104 篇幅约束，别给快照添噪声）。"""
    return f"""---
id: {id}
title: {id}
type: event
author: dataset-v1
date: 2026-09-23
status: {status}
load_bearing: false
when: {when}
when_sort: {when_sort}
event_kind: {kind}
{legs}canon_refs: []
conflicts_with: []
depends_on: []
superseded_by: null
ai_assisted: false
---

{body}
"""


def dep(id, kind, critical=True):
    return (id, kind, critical)


def dep_list(deps):
    if not deps:
        return "[]"
    lines = [""]
    for id, kind, critical in deps:
        c = "true" if critical else "false"
        lines.append(f"  - id: {id}\n    kind: {kind}\n    critical: {c}")
    return "\n".join(lines)


def conflict_list(refs):
    """refs: [(id, stance|None), ...]"""
    if not refs:
        return "[]"
    simple = [r for r in refs if isinstance(r, str)]
    if len(simple) == len(refs):
        return "[" + ", ".join(simple) + "]"
    lines = [""]
    for r in refs:
        if isinstance(r, str):
            lines.append(f"  - {r}")
        else:
            id, stance = r
            lines.append(f"  - id: {id}\n    stance: {stance}")
    return "\n".join(lines)


ME = {}  # 中土
WE = {}  # 维斯特洛

# ============ 中土 ============

ME["gondor-realm"] = ("faction", "canon", "political", True, """\
刚铎王国，第三纪元末的南方人类王国。王位空悬近千年，由执政宰相世家代管。
值得注意的是：全书对刚铎的税收、王室财政、货币发行没有任何记载——
这个王国养着常备军和七环城，却没有任何条目能说明钱从哪来。
lint 应当在此处报告空中楼阁：一个 political 层承重墙，下面没有 fiscal 支点。""",
"[]", "[]", [("fief-muster-system", "manpower", True)])

ME["fief-muster-system"] = ("faction", "canon", "military", True, """\
刚铎的封邑征召制：南方各封邑按定额出兵。佩兰诺战前的援军清单逐项可数：
洛斯阿尔那赫斧手二百（书中明言这是该地的什一征额）、林罗谷三百、
莫松德弓手五百、伊西尔渔民一百、品那斯格林三百、多阿姆洛斯步兵七百加骑士一营。
原文收束：'不足三千，再无来者。' 制度有效，但总量天花板清晰可见。""",
"[gondor-realm]", "[]", [("rohan-oath-2510", "legitimacy", True)])

ME["rohan-oath-2510"] = ("event", "canon", "political", True, """\
第三纪元2510年，执政宰相奇瑞安以卡伦那松全域赠予伊奥希奥德人，
换取永世军事同盟。伊奥梅尔誓言原文：'汝之敌即我之敌，汝之急即我之急'。
五百年后佩兰诺之战，希奥顿仍视其为神圣义务。触发机制：烽火台与红箭。
一条封建契约跨五个世纪仍是军事动员的法律基础——制度承重墙的标准样本。""",
"[]", "[]", [])

ME["mordor-host"] = ("faction", "canon", "military", True, """\
魔多的围城大军。粮食来自纳恩奴隶农庄（山姆与弗罗多亲眼所见的南方大田），
兵员纪律不依赖粮饷而依赖索伦的中央意志支配。战后纳恩奴隶被埃莱萨释放，
纳恩成为独立土地——这条供应链在战后整体失效。""",
"[]", "[]", [("nurn-slave-fields", "production", True),
           ("sauron-dominion", "x-will-binding", True)])

ME["nurn-slave-fields"] = ("location", "canon", "production", True, """\
纳恩低地的奴隶劳作大田，四河注入努尔能内陆海，土壤远比戈埚洛斯高原肥沃。
'辽阔国土南方的大片奴隶耕作之田'（《魔影之地》）。
农庄到前线军营的运量与损耗率：无记载。""",
"[]", "[]", [])

ME["sauron-dominion"] = ("faction", "canon", "ideology", True, """\
索伦的支配体系。对兽人是中央意志的蚁群式支配（'使兽人几成蚁群之生，
其控制远胜魔苟斯'，《魔苟斯之戒》p.417），对努门诺尔人与东方人类则是
利诱与许愿：延寿、秩序、复仇。恐惧是底色但非唯一手段——
同一专制者对不同对象用不同的供养关系，这正是 kind 分辨率的试金石。""",
"[]", "[]", [("the-one-ring", "legitimacy", False)])

ME["the-one-ring"] = ("item", "canon", "ideology", True, """\
至尊魔戒：统治权证书与力量电池的复合体。功能有三：储存索伦力量本源、
作为支配其余诸戒及其持有者的意志总线、以及对'诸戒之王'地位的合法性宣称。
它不是产能工具；索伦对兽人的控制不靠它（见 sauron-dominion），
它支配的是持戒者网络。一个物件同时承载 resource 与 legitimacy 两种 kind。""",
"[]", "[]", [("sauron-dominion", "resource", False)])

ME["minas-tirith"] = ("location", "canon", "economy", True, """\
米那斯提力斯，白城，七环之城。人口书内无数值（外部考据估一万五至三万，
置信度低；'半空'的描写暗示容量远大于现人口）。粮食来自佩兰诺田园
（'townlands were rich'）与安都因河运，咽喉在奥斯吉利亚斯渡桥——
渡桥失守即粮道被掐。佩兰诺围城期间的粮价与配给：无记载（stylistic missing，
托尔金根本不写后勤）。""",
"[]", "[]", [("pelennor-fields", "resource", True)])

ME["pelennor-fields"] = ("location", "canon", "resource", True, """\
佩兰诺平野：环绕白城的牧农田园，拉马斯外墙圈出的近郊产粮区。
围城前被主动弃守收缩，田野付诸敌蹄。""",
"[]", "[]", [])

# 奥克起源：三个正典版本互斥，全部保留
ME["orc-origin-silmarillion"] = ("event", "canon", None, False, """\
1951 年《精灵宝钻》选定版：奥克源于被魔苟斯俘获并扭曲的精灵。
克里斯托弗·托尔金的编辑定本，流传最广的正典。""",
"[]", conflict_list([("orc-origin-corruption", "official"),
                     ("orc-origin-myths-transformed", None)]), [])
ME["orc-origin-corruption"] = ("event", "canon", None, False, """\
正文版（奇立斯乌苟之塔，弗罗多对山姆）：'暗影只能嘲弄，不能创造……
它只是毁坏了他们，扭曲了他们。' 明确否定泥土/石头造物的旧版，
但未指明被腐化者究竟是精灵、人类还是兽类。""",
"[]", conflict_list([("orc-origin-silmarillion", "heretic"),
                     ("orc-origin-myths-transformed", None)]), [])
ME["orc-origin-myths-transformed"] = ("event", "canon", None, False, """\
1950 年代后期 Myths Transformed 文本群（VII-X）：起源在精灵、人类、
兽类与混合说之间反复，托尔金至死未定。1963 年拍卖流出信件孤证：
'想必存在女兽人……只是无人知晓。' 繁殖方式一栏：全谱系 missing。""",
"[]", conflict_list([("orc-origin-silmarillion", None),
                     ("orc-origin-corruption", None)]), [])

# 蓝袍巫师：双正典互斥
ME["blue-wizards-ut"] = ("character", "canon", None, False, """\
UT《伊斯塔利》版：阿拉塔尔与帕蓝多，第二纪元约1600年赴东方，
下落不明，'有人认为他们堕入邪恶成了索伦的仆从'。""",
"[]", conflict_list([("blue-wizards-pome", "official")]), [])
ME["blue-wizards-pome"] = ("character", "canon", None, False, """\
PoME《晚期著作》版：改名莫林赫塔与罗梅斯塔莫（'灭暗者'与'助东者'），
同约第二纪元1600年赴东方，使命是削弱索伦在东方的势力，
且'似乎成功了'——从失败翻案为成功，名字与命运全部冲突。""",
"[]", conflict_list([("blue-wizards-ut", "heretic")]), [])

# ============ 维斯特洛 ============

WE["iron-throne"] = ("faction", "canon", "political", True, """\
七国铁王座。劳勃时代财政已空：国库靠举债维持，实际财技操盘手自小指头始。
王座的军事存在（王领兵力、守夜人拨款、海政）全部悬于财政收入一线，
而收入一线早已变成债务黑洞。""",
"[]", "[]", [("crown-debt-agot", "fiscal", True)])

WE["crown-debt-agot"] = ("event", "canon", "fiscal", False, """\
AGOT《Lord Snow》口径：王冠负债六百万金龙，其中三百万欠兰尼斯特。
小指头对奈德交底。距劳勃登基仅约十五年。""",
"[]", "[crown-debt-affc]", [])
WE["crown-debt-affc"] = ("event", "canon", "fiscal", False, """\
AFFC 提利昂口径：'我们欠他们数千万'。从六百万到数千万，
约十倍级差，书中无任何过程交代。两口径并存，不加裁决——
可注记'修辞夸张/通胀'的翻译方向，但数字本身互斥。""",
"[]", "[crown-debt-agot]", [])

WE["iron-bank"] = ("faction", "canon", "economy", True, """\
布拉佛斯铁金库。放贷逻辑原文：'王侯若不能偿还铁金库，
就会有新的王侯凭空坐上他们的王位。' 瑟曦停付即转投史坦尼斯
（条件：登基后承认铁王座债务）；同时向守夜人放款购粮——
机构对国家与组织一视同仁，只问偿还能力。""",
"[]", "[]", [("braavos-free-port", "economy", True)])

WE["stannis-north-campaign"] = ("event", "canon", "military", True, """\
史坦尼斯的北境军事行动。资金完全依赖铁金库贷款，
而贷款的触发器是瑟曦的违约决定——一条政治决定撬动两个战场的资金流。""",
"[cersei-default]", "[]", [("iron-bank", "fiscal", True)])

WE["cersei-default"] = ("event", "canon", None, False, """\
瑟曦单方面停付铁金库债务的政治决定。直接后果：铁金库转投史坦尼斯，
铁王座再融资通道关闭。建模注记：本条与债务的关系是"作用于"而非"被供养"，
故用 canon_refs 而非 depends_on。""",
"[crown-debt-affc]", "[]", [])

WE["kings-landing"] = ("location", "canon", "economy", True, """\
君临，人口约五十万（提利昂口径，ASOS；马丁自定标：大于中世纪伦敦巴黎，
小于君士坦丁堡）。粮食全靠输入：玫瑰大道陆路加海运，无战略存粮——
黑水河战前海路被掐，面包暴乱直接冲击红堡，一句话证明输入线即生命线。""",
"[]", "[]", [("roseroad-grain", "resource", True)])

WE["roseroad-grain"] = ("location", "canon", "resource", True, """\
玫瑰大道：河湾地到君临的陆路粮道。河湾地是七国粮仓，
谁控制玫瑰大道，谁就捏着君临的饭碗。""",
"[]", "[]", [])

WE["braavos-free-port"] = ("location", "canon", "economy", True, """\
布拉佛斯自由港：银行业（铁金库）、保险业（钥匙持有者）、造船（兵工厂）、
渔业与海运贸易多支柱。政治底座是逃亡奴隶建城与永久禁奴法理——
这使它对奴隶湾政权有结构性敌意，也构成吸引自由贸易的身份资本。""",
"[]", "[]", [])

WE["night-watch-order"] = ("faction", "canon", "military", True, """\
当代守夜人：全团不足千人，十九座城堡常驻者仅三座
（黑城堡、影子塔、东海望）。守卫对象是三百英里长、七百尺高的长城。""",
"[]", conflict_list([("the-wall-scale", None)]),
[])

WE["the-wall-scale"] = ("location", "canon", None, False, """\
长城本体设定：七百尺高、三百英里长、十九座城堡。
筑城者时代的组织能力 vs 当代守夜人不足千人的规模落差无解——
可读作叙事性退化（degradation），亦可读作解释缺失（missing），两解并存。""",
"[]", conflict_list([("night-watch-order", None)]), [])

WE["robb-host-theon"] = ("event", "canon", "military", False, """\
萝卜南下兵力·席恩口径：两万。""",
"[]", "[robb-host-ledger]", [])
WE["robb-host-ledger"] = ("event", "canon", "military", False, """\
萝卜南下兵力·分项加总口径：封邑逐项合计约一万七千，
绿叉河后回流计算约一万八千。与席恩口径差幅超一成，三方均无解释。""",
"[]", "[robb-host-theon]", [])

WE["wight-army"] = ("faction", "canon", "military", True, """\
尸鬼军团：复活尸体组成的不死者大军。无粮食需求、无睡眠、士气恒定，
且随身携冬（'寒冷随他们而来'）——魔法替代后勤的双向豁免。
一切活人大军都受粮食与债务链条约束，唯独它的成本函数里没有 food 项。""",
"[]", "[]", [("the-others-magic", "x-magic-logistics", True)])

WE["the-others-magic"] = ("faction", "canon", "ideology", True, """\
异鬼的寒冰魔法：复活死者、改变环境补给条件的超自然力量源头。
注意其位于 ideology 层——它是信仰之外的另一类'非物质的支配力'，
kind 实验值 x-magic-logistics 的供给方。""",
"[]", "[]", [])

WE["the-north"] = ("faction", "canon", "political", True, """\
北境。地广人稀，封臣征召制，动员总量天花板低（萝卜只能拉出一两万）。
长冬存粮制度：口头焦虑无数，具体制度几乎无记载——
冬市镇入冬迁出、曼德勒丰收宴、卡林湾沼泽存粮，皆零星线索不成体系。
与刚铎财政并列为'大师共同的盲区'：political 承重墙下缺 fiscal 支点。""",
"[]", "[]", [("robb-host-ledger", "manpower", False)])

# ---- 期初断言与流水的实体卡（协议 1.2；lb 全 False，不给 CA503 添戏）----

WE["house-tully"] = ("faction", "canon", "political", False, """\
徒利家族，河间地的统领世家，奔流城公爵，族语'家族、责任、荣誉'。
河间地四战之地，无险可守，徒利家的地位靠的是与史塔克、艾林两家的
姻亲同盟，而不是天险与体量。凯特琳与莱莎的婚事把这个家族织进了
北境与谷地的权力网，也让它在五王之战里首当其冲。族语把'责任'排在
'荣誉'之前，这个次序本身就是河间地生存之道的注脚：先还债，再谈脸面。
红婚之后家业尽毁，奔流城易主，族人流散——靠关系网立足的家族，
关系网断时败得比谁都快；到战争后期，连守住自家渡口都成了奢望，
网断的时候，连收网的人都没有。""",
"[]", "[]", [], "[riverrun]")

WE["riverrun"] = ("location", "canon", None, False, """\
奔流城，徒利家族的家堡，坐落于腾石河与红叉河交汇处。两河夹峙使它能
被水围成孤岛：拉起水闸，城下即成泽国，攻城方须分兵三处，彼此难以呼应。
书中两次围城（五王之战初期与红色婚礼之后）都演示了这一点。攻城方想
拿下它，要么备足三份粮草分驻三岸，要么指望城里先断粮——两种都慢，
所以泰温与佛雷后来都选了更省事的办法：在婚礼上下手，绕过城墙。
它是河间地少数经得起长期围困的据点，也是徒利家族语的具体化身——
占地利而不占体量，守得住却难以对外扩张；城墙立在水上，安危系于人心。""",
"[]", "[]", [])

WE["eddard-stark"] = ("character", "canon", None, False, """\
艾德·史塔克，临冬城公爵，北境守护，劳勃起义的副帅与后来的国王之手。
他的行事准则是荣誉与责任，而这在君临的权力场里恰是致命短板：
他提前警告瑟曦，把先手让给了对手；他拒绝在名册上做半点手脚，
把退路一条条亲手堵死。299 AC 被乔佛里下令处决，首级挂上枪尖——
北境与铁王座之间仅存的信任纽带随之断裂，五王之战从此没有了
媾和的可能。寒冰巨剑随他南行又随囚车北返，最终被泰温下令熔成
两把新剑。他一生没打过一场败仗，却输掉了只有他才想守的那盘棋；
账记到这里，北境再无可谈的人。""",
"[]", "[]", [], "[ice-sword]")

WE["robert-baratheon"] = ("character", "canon", None, False, """\
劳勃·拜拉席恩，283 AC 戴上王冠的起义领袖。三叉戟河一战亲手击杀雷加，
靠战功、血统与奈德、琼恩·艾林的同盟坐上铁王座。登基之后迅速对治绩
失去兴趣：比武、打猎、宴饮，一场接一场的盛会开销无度，把国库花成
债务黑洞，把朝政交给御前会议，把警觉交给酒杯。他对兰尼斯特的倚重
与对瑟曦的冷遇同时加深，王朝的平衡全靠他个人的存在维持——
他死于猎场的那头野猪，直接揭开了五王之战的序幕。打赢王座的人，
恰恰是最不想要王座日常的那个人；他要的是王冠加冕那一刻，
从来不是王座背后那本账。""",
"[]", "[]", [], "[iron-throne]")

WE["stannis-baratheon"] = ("character", "canon", None, False, """\
史坦尼斯·拜拉席恩，劳勃的二弟，龙石岛公爵。以严酷、记仇与不妥协著称，
自认是铁王座的合法主人。瑟曦停付铁金库债务后，他接受了铁金库的
贷款条件：登基即承认王冠旧债。这笔钱支撑了他的北境战事——
雪衣马队、雇船与粮草，还有一路向北的补给船期。他对名分的执着到了
自我消耗的地步：明明兵力最弱，却不肯在任何条款上让步，
也不肯用一句软话换一支援军。公正是他唯一的旗帜，也是他唯一的资产；
风息堡之围的旧账，他记了一辈子——公正的旗帜不值钱，
值钱的是有人肯为这面旗出真金白银。""",
"[]", "[]", [], "[stannis-loan-gold]")

WE["ice-sword"] = ("item", "canon", None, False, """\
寒冰，史塔克家祖传的瓦雷利亚钢巨剑，长约六尺，宽逾人掌，
剑身有波纹状暗纹，夜色里剑锋泛着幽光。它在临冬城传承四百年，
是北境守护身份的信物，只在行刑与大战时出鞘。艾德·史塔克用它
处决守夜人逃兵，后来它被用来处决艾德本人。泰温·兰尼斯特得到它
之后将其熔成两把新剑——守誓者与寡妇之嚎，一把给了詹姆，
一把将赴多恩。一件信物被敌手拆解重铸，是名分易手最直白的物证：
剑还在，持剑的家族已天各一方；熔剑的炉火熄了，名分的火还没熄，
两把新剑各自的去向，是另一条流水的开头。""",
"[]", "[]", [])

WE["stannis-loan-gold"] = ("item", "canon", None, False, """\
铁金库贷给史坦尼斯的那笔资金（拟物条目）。触发条件是瑟曦的停付决定：
铁王座不再偿债，铁金库便按'另立新王'的惯例物色下家。布拉佛斯特使
泰楚·奈斯托斯在长城下找到史坦尼斯，条件写得明白：他日登基，
承认并偿还铁王座的全部旧债，分文不少。这笔钱换来雇佣兵、船只与补给，
支撑了从长城到临冬城外的整场北境战事——一笔贷款撬动一个战场，
是铁金库放贷逻辑的标准样本：不站队，只站偿还得起的那一边。
账面上的数字不大，押上的却是一个王国的名分；
回执已经寄出，兑现在下一卷的战场上。""",
"[]", "[]", [])

WE["house-stark"] = ("faction", "canon", None, False, """\
史塔克家族，临冬城主人，北境数千年的守护世家，族语'凛冬将至'。
它的根基不是财富而是名分：北境各封臣对狼家的忠诚建立在漫长的
共处与偶尔的决断上——恐怖堡的造反被平定过，荒冢屯的怨怼被安抚过，
旧账都记着，却都翻过去了。艾德死后这个家族迅速失血：罗柏在孪河城
遇害，家堡被焚，族人四散。但'北境永不遗忘'的另一面也随之显现：
各封臣明里顺服波顿，暗里仍以狼家为念。一个家族的存续，
靠的不是城墙，而是别人愿不愿意替它记着——族语不说'凛冬已至'
而说'将至'，这个家族记挂的从来都是后账。""",
"[]", "[]", [])

WE["robb-host-army"] = ("faction", "canon", None, False, """\
罗柏·史塔克的南下大军本体（与 robb-host-theon / robb-host-ledger
两张兵力口径卡互为表里：那两张记'多少人'，这张记'这支部众'）。
由北境各封臣的扈从拼成，步兵为主、骑兵为锋，绿叉河分兵之后主力
西进呓语森林，连战连捷，营中还押着一位兰尼斯特。它的短板在补给
与人心：深入河间地之后粮草难继，各封臣的家眷又都留在北方，
而佛雷家的敌意因悔婚不断累积。298 AC 经孪河城南返时，
它在红色婚礼上一夜瓦解——赢下了每一场战斗，输掉了整场战争；
部众散了，那两张口径卡还在。""",
"[]", "[]", [])

WE["the-twins"] = ("location", "canon", None, False, """\
孪河城，佛雷家族的家堡，绿叉河上唯一的渡口：两座一模一样的城堡
隔河对峙，中间以石桥相连，桥上还有塔楼与闸门。谁要过大军，
谁就得答允瓦德·佛雷的条件——这个地利让一个人丁兴旺却名声不佳的
家族握有超出体量的筹码，也让'迟到的佛雷'的讥诮传了七国。
罗柏当年以婚约换通行，悔婚之后再想南返，佛雷家开出的价码就变成了
红色婚礼。渡口即力量：卡着别人必经之路的地方，本身就是一种收成；
而收成什么时候落袋，由守渡口的人说了算——两座城堡一条桥，
桥上的闸门比两边的城墙都值钱。""",
"[]", "[]", [])

# ---- 九笔流水（when_sort 用故事内纪年 AC；断言与流水推出的最终持有者一致）----

WE["ev-wall-built"] = evm("ev-wall-built", "create", "约 -8000 AC", -8000, """\
筑城者布兰登率巨人与森林之子筑起长城，在绝境以北立下七国的北疆屏障。
关于它的筑成年代与工艺，书中只有传说口径：冰与石之外据说还织入了
古老魔法，基座深处的石门只认守夜人的誓言。这笔'期初资产'至今是整个
防御体系的底座——守夜人只是后来的看管人，而且看管得一年不如一年。
把它记为 create 而不是自古存在，是因为世界的账需要一笔起点：
屏障不是从来就有的，它是被造出来的；被造出来的东西，就总有
造价、工期与维护这三笔后账，哪怕书里一笔都不肯写。起点立住了，
后账慢慢算。""",
"object:\n  - the-wall-scale\n")

WE["ev-riverrun-granted"] = evm("ev-riverrun-granted", "grant", "1 AC", 1, """\
征服者伊耿平定河间地之后，把三叉戟河流域的统辖名分授予率先归附的
徒利家：奔流城从此是河间地统领的座城，三叉戟诸侯的封君由此换姓。
这类'名分授予'记作 grant：它不移交实物的钥匙，移交的是'谁说了算'
的凭证。河间地诸侯从此向徒利家效忠——徒利家的地位源头是一笔王恩，
而不是打下来的家业，这也埋下了它在乱世里缺乏铁杆根基的伏笔：
恩典能给的东西，换个王就能收回；三百年后，这话在孪河城应验了两次。
名分的源头记下了，往后的得失才有地方挂账——这正是流水要记 grant
的理由。""",
"by:\n  - iron-throne\nto:\n  - house-tully\nobject:\n  - riverrun\n")

WE["ev-ned-born"] = evm("ev-ned-born", "birth", "263 AC", 263, """\
艾德·史塔克出生，临冬城公爵瑞卡德的次子。八岁被送往鹰巢城做养子，
与劳勃·拜拉席恩一同受教于琼恩·艾林——这段少年情谊后来决定了
北境与风暴地的同盟，也决定了劳勃起义的走向，更决定了他后半生
每一个选择的底色。次子原本不接班：长兄布兰登死于君临之后，
公国、婚约与责任一并落到他肩上，他接过的不只是领地，
还有一份他没挑过的人生。他的出生本身平淡，但这本账要从人记起：
后来的每一笔名分流转，都挂在他名下。这本账从他记起，却不是由他结清；
往后的每一笔，都要别人替他还。""",
"object:\n  - eddard-stark\n")

WE["ev-robert-crowned"] = evm("ev-robert-crowned", "grant", "283 AC", 283, """\
劳勃在君临加冕，铁王座的名分从坦格利安转到拜拉席恩。授出方这一栏
写的是 iron-throne 自身：王座作为七国名分的总枢纽，是这场授予真正的
'经手人'——琼恩·艾林与奈德只是促成者，泰温的献城只是临门一脚。
名分依据来自三条：战功（三叉戟河）、血统（祖母是坦格利安）、
与既成事实（君临已下）。这场 grant 是后头一切账的起点：债务、
贷款、叛旗，全都挂在这顶王冠的名下；王冠换姓的这一刻，
七国的账本也换了记账人，只是新旧两本账的窟窿，都要后人来填。
加冕是账本上最贵的一笔进账，也是最贵的一笔欠账。""",
"by:\n  - iron-throne\nto:\n  - robert-baratheon\nobject:\n  - iron-throne\n")

WE["ev-ice-to-ned"] = evm("ev-ice-to-ned", "transfer", "290 AC", 290, """\
寒冰由史塔克家传到艾德手里（实际接剑发生在 282 年布兰登与瑞卡德死后，
此处按故事内惯用纪年取整）。这类'家族信物移交现任当家'记作 transfer：
实物易手，名分随行，临冬城的钥匙与北境的安危也一并换了主人。
此剑在艾德手中的用途有明载的两类：处决（守夜人逃兵威尔）与征战。
它在 297 年被入库保管（见 ev-ice-in-keep），299 年主人死后被缴获，
最终被熔成两把新剑——信物的存续比主人长，而它的每一次易手，
都对应北境账本上一笔抹不掉的折损。剑的账，比人的账长。""",
"by:\n  - house-stark\nto:\n  - eddard-stark\nobject:\n  - ice-sword\n")

WE["ev-ice-in-keep"] = evm("ev-ice-in-keep", "custody", "297 AC", 297, """\
艾德南下就任国王之手，寒冰留在临冬城，由史塔克家入库保管。
记作 custody 而不是 transfer：剑的所有名分仍在艾德名下
（所以卡上的 owns 断言写的是艾德），变的只是'谁在看着它'——
管家、教头与侍卫轮值，钥匙留在临冬城的库里。保管与持有分开记账，
正是为了不把'托人看家'误读成'家产易主'。后来城破剑失，
这条保管记录也随之作废——但它解释了 297 到 299 年间
剑与主人为何天各一方，也解释了缴获它的为什么不是它的主人。
城破之后，这条记录成了它被人记得的最后下落。""",
"by:\n  - eddard-stark\nto:\n  - house-stark\nobject:\n  - ice-sword\n")

WE["ev-robb-marches"] = evm("ev-robb-marches", "move", "298 AC", 298, """\
罗柏率大军经孪河城南返。绿叉河分兵时他曾以婚约换得佛雷家的通行
与出兵，悔婚之后这支部众再度需要渡口，价码已今非昔比——瓦德·佛雷
要的不只是道歉，还有一场当众的羞辱。记作 move：客体是'这支部众'
（robb-host-army，与两张兵力口径卡分账），目的地是孪河城。
渡河之后的事写进了红色婚礼：佛雷家以宴会为饵，一夜之内把这支部众
连同它的统帅一起抹掉——一个渡口卡住了一支大军的生死，
也卡住了整个北境的前途。渡口过了，命没了；
这笔 move 是这支大军最后的位置记录。""",
"object:\n  - robb-host-army\nto:\n  - the-twins\n")

WE["ev-ned-executed"] = evm("ev-ned-executed", "death", "299 AC", 299, """\
艾德·史塔克在贝勒大圣堂前被处决。他已按瓦里斯的劝说认罪以换取
披上黑衣，乔佛里临时变卦下令斩首，伊林·派恩用的正是寒冰——
用主人自己的剑处决主人，是这场处决最刺耳的一笔。记作 death：
从这一刻起，任何再把他写进 by 的事件都是「死人做活事」（CA705）。
他名下的账并未清零：寒冰被缴获、北境叛旗竖起、五个子女的流离，
全都以这一刻为分水岭——人没了，账还在往下滚，而且滚得更快了。
乔佛里为这一剑付出的代价，写在后面每一卷里：北境不再有人谈归顺，
河间也不再有人谈中立。""",
"object:\n  - eddard-stark\n")

WE["ev-stannis-loan"] = evm("ev-stannis-loan", "transfer", "300 AC", 300, """\
铁金库把贷款交付史坦尼斯。记作 transfer：资金（拟物为
stannis-loan-gold）的所有权从金库移到他名下，条件是他日登基即
承认王冠旧债，连本带利，分文不少。这笔钱随即变成雇船、佣兵与粮草，
支撑从长城到临冬城外的整场战事，也把他更深地绑上铁金库的战车。
铁金库的账从不看人下菜：瑟曦停付在前，它就按老规矩另寻下家——
'王侯若不能偿还铁金库，就会有新的王侯凭空坐上他们的王位'，
这笔 transfer 是那句话的执行记录，也是瑟曦那张停付令的回执。""",
"by:\n  - iron-bank\nto:\n  - stannis-baratheon\nobject:\n  - stannis-loan-gold\n")

# ---- x- 实验事件（协议泄压阀：backlog B1/B2 的攒案例轮，2026-10-21）----

WE["jon-snow"] = ("character", "canon", None, False, """\
琼恩·雪诺，艾德·史塔克的私生子，临冬城里永远坐末席的那个。
他的人生选择几乎都围绕名分二字展开：既然家业无望，就去一个
以出身清零的地方——长城。298 AC 披上黑衣，从守夜人新兵做起，
后来被派去当事务官而不是游骑兵，一度视为羞辱，实为熊老的刻意培养。
他的故事线全程是'身份'与'誓言'的拉扯：守夜人的誓言要求舍弃家族，
而他的家族在他离开后一路破碎。这条线上每个节点都是 join/leave
的样本。私生子这个出身，北境没人当面提，但也没人忘；他自己更没忘。
白灵跟在他脚边，比任何名分都忠实。""",
"[]", "[]", [], "[]", "[night-watch-order]")

WE["will-deserter"] = ("character", "canon", None, False, """\
威尔，守夜人游骑兵，《权力的游戏》序章里那个从长城以北逃回来的人。
他看见了异鬼，活着回来已是奇迹，但守夜人的法度不看这个：
逃兵就是逃兵。他在临冬城外被艾德·史塔克亲手处决，寒冰出鞘。
他是这本书里第一个为'誓言与活命冲突'付账的人——leave 的案例
就该记他：离开守夜人不是辞职，是叛誓，代价写得清清楚楚。
他的死常被读者翻过去，但序章的每一句都在给后面上账：异鬼是真的，
而知道的人死在了'规矩'手里。守夜人失去的不止一个游骑兵，
是第一条活口供。长城上下的信息差，从这一剑开始累积。""",
"[]", "[]", [])

WE["oathkeeper"] = ("item", "canon", None, False, """\
守誓者，寒冰熔成的两把新剑之一。泰温·兰尼斯特把它给了詹姆，
詹姆又把它转赠布蕾妮，命她去寻回并保护史塔克家的女儿——
一把由史塔克家传剑熔成的剑，转身去护史塔克家的人，
名分与实物在这里打了个结。剑身有瓦雷利亚钢的波纹，狮头剑首。
它的每一次易手都不是简单的 transfer：赠送者都在借这把剑说一句话。
布蕾妮带着它上路时，并不知道自己要去兑现的是谁的誓言——
詹姆没说全，她也没问全。这把剑后来见的血不多，见的心结不少；
一身铁皮下裹着的，全是别人没说完的话。""",
"[]", "[]", [])

WE["widows-wail"] = ("item", "canon", None, False, """\
寡妇之嚎，寒冰熔成的另一把。泰温把它给了乔佛里当婚礼礼物——
乔佛里死于自己的婚宴，这把剑几乎没有出鞘记录，之后归了托曼。
它的名字来自那场面：红色婚礼与紫色婚礼之间，北境与王城的未亡人们。
与守誓者对照着看：同源的两把剑，一把被赠来践行誓言，
一把被赠来炫耀武力，走向完全不同的叙事用途。乔佛里给它起名的
那一刻，席间没有人笑。一把剑叫什么，往往比它砍过什么更说明
持剑的人想要什么。它后来的命运是挂在墙上——名分太大，没人敢真用；
挂着它的那面墙，比它见过的战场多。""",
"[]", "[]", [])

WE["ev-jon-joins"] = evm("ev-jon-joins", "join", "298 AC", 298, """\
琼恩·雪诺北上长城，在守夜人军团的新兵誓约下披上黑衣。
join 的腿表就是从这笔账定型的：by 记加入者本人，to 记加入的组织
（人是 by，与 CA705 同一条腿——死人不能入伙；组织的'同意收人'
一侧没有腿，v0 只记事实侧）。加入之后，他名下的账换了算法：
家族名分按誓言清零，守夜人的口粮与职责开始挂账。
（backlog B2 的攒案例事件，协议 1.6 转正——它是 join 这个词进词表
的理由本身：先有真实的一笔账，后有词表里的一个名字。）长城以北的风，
从他踏进黑城堡那天起，就是另一本账了。""",
"by:\n  - jon-snow\nto:\n  - night-watch-order\n")

WE["ev-will-deserts"] = evm("ev-will-deserts", "leave", "297 AC", 297, """\
威尔当了四年游骑兵，在长城以北看见了不该存在的东西，转身南逃。
leave 的腿表从这笔定型：by 是离开者，from 是离开的组织。
它与 join 不对称的地方值得记下：join 是双向自愿（组织收人），
leave 可以是单方面的（叛逃不需要守夜人同意）。这笔账的结局写在
临冬城外：逃兵被处决，寒冰出鞘——'离开'这个事件的代价
随世界规则而不同，工具只记账，不评价。
（backlog B2 的攒案例事件，协议 1.6 转正——leave 与 join 的
不对称（单方面 vs 双向）就写在这笔账的注脚里。）""",
"by:\n  - will-deserter\nfrom:\n  - night-watch-order\n")

WE["ev-ice-reforged"] = evm("ev-ice-reforged", "transform", "301 AC", 301, """\
泰温·兰尼斯特下令把寒冰熔了，铸成两把新剑。transform 的腿表就是从
这笔账定型的：object 是旧身份（寒冰，存在窗口到此关闭），result 是
新身份列表（守誓者与寡妇之嚎，各自的窗口从这里打开）——旧身份死、
新身份生、物质延续。注意流水不替新身份接管旧账：两把新剑此时的
持有者与位置账上没有，要记就再写一笔 transfer——v0 不猜。
（backlog B1 的攒案例事件，协议 1.7 转正；它是 transform 这个词
进词表的理由本身——先有账，后有名。）""",
"object:\n  - ice-sword\nresult:\n  - oathkeeper\n  - widows-wail\n")


def write_world(path: Path, entries: dict) -> None:
    if path.exists():
        shutil.rmtree(path)
    (path / "entries").mkdir(parents=True)
    for id, spec in entries.items():
        if isinstance(spec, str):
            (path / "entries" / f"{id}.md").write_text(spec, encoding="utf-8")
            continue
        (type_, status, layer, lb, body, refs, conflicts, deps) = spec[:8]
        owns = spec[8] if len(spec) > 8 else "[]"
        member_of = spec[9] if len(spec) > 9 else "[]"
        # kind=legitimacy 拆成 derives_legitimacy_from（拆分后的关系名，见协议 §9 修订记录）
        material = [d for d in deps if d[1] != "legitimacy"]
        legit = [d for d in deps if d[1] == "legitimacy"]
        depends = dep_list(material) if material or not legit else None
        legitimacy = "".join(
            f"\n  - id: {d[0]}\n    critical: {'true' if d[2] else 'false'}"
            for d in legit)
        title = id
        text = fm(id, title, type_, status, layer=layer, load_bearing=lb,
                  canon_refs=refs,
                  conflicts=conflicts if conflicts.startswith("[") or conflicts == "[]"
                  else conflict_list([]),
                  depends=depends, owns=owns, legitimacy=legitimacy,
                  member_of=member_of)
        (path / "entries" / f"{id}.md").write_text(text + body, encoding="utf-8")


write_world(ROOT / "world-middle-earth", ME)
write_world(ROOT / "world-westeros", WE)
print(f"middle-earth: {len(ME)} entries, westeros: {len(WE)} entries")
