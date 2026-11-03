"""Builds the Starling guide website (site/index.html) from tools/guide_template.html and the real command catalog.

Run:  python tools/build_guide.py
The command tables come from control/catalog.py, so a new command shows up in the guide by itself.
The hand-written tables (routes, chat and so on) are the EXTRA list below: add new sayings there.
"""
import sys, re, html, os
from pathlib import Path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from control import catalog
M = catalog.MACROS


def first(t):
    for k, v in M.items():
        t = t.replace('{%s}' % k, v)
    t = re.sub(r'\[([^\]]*)\]', '', t)
    for _ in range(3):
        t = re.sub(r'\(([^()]*)\)', lambda m: m.group(1).split('|')[0], t)
    t = t.replace('?', '')
    return ' '.join(t.split())


C = {c.id: c for c in catalog.CATALOG}
OVER = {
    'fss_enter': ['Open the FSS', 'Close the FSS'], 'speed_0': ['All stop'], 'speed_50': ['Set throttle to 50'],
    'speed_75': ['Set throttle to 75'], 'speed_100': ['Set throttle to 100'],
    'hud_mode': ['Switch to analysis mode', 'Switch to combat mode'],
    'power_engines': ['Pips to engines'], 'power_weapons': ['Pips to weapons'], 'power_systems': ['Pips to systems'],
    'power_reset': ['Balance the power'], 'heatsink': ['Fire heatsink'], 'boost': ['Boost'],
    'supercruise': ['Engage supercruise'], 'hyperspace': ['Engage hyperspace'],
    'request_docking': ['Request docking'], 'auto_launch': ['Launch'], 'deploy_nomad': ['Deploy the Nomad'],
    'plot_waypoint': ['Plot the next waypoint'], 'show_off': ['Show off'],
    'left_panel': ['Open the left panel'], 'right_panel': ['Open the right panel'],
    'comms_panel': ['Open the comms panel'], 'radar_panel': ['Open the role panel'],
    'radar_range_up': ['Increase the radar range'], 'radar_range_down': ['Decrease the radar range'],
    'orbit_lines': ['Toggle orbit lines'], 'vc_hide_all': ['Hide all overlays'], 'vc_show_all': ['Show overlays'],
    'foot_jump': ['Hop'], 'foot_grenade_frag': ['Select frag grenades'], 'foot_grenade_emp': ['Select EMP grenades'],
    'foot_grenade_shield': ['Select shield grenades'], 'foot_grenade_throw': ['Throw grenade'],
    'gear': ['Deploy the landing gear', 'Retract the landing gear'], 'weapons': ['Deploy weapons', 'Retract weapons'],
    'scoop': ['Deploy the cargo scoop', 'Retract the cargo scoop'], 'lights': ['Turn on the lights', 'Turn off the lights'],
}
CAREFUL = {'supercruise', 'hyperspace', 'request_docking', 'auto_launch', 'deploy_nomad', 'plot_waypoint', 'show_off',
           'foot_grenade_throw'}


def examples(c):
    if c.id in OVER:
        return OVER[c.id]
    out = []
    for intent in ('on', 'off', 'press'):
        ph = c.phrases.get(intent)
        if ph:
            out.append(first(ph[0]).capitalize())
    if not out and c.phrases.get('toggle'):
        out.append(first(c.phrases['toggle'][0]).capitalize())
    return out


def name(c):
    label = c.label.strip()
    return label[:1].upper() + label[1:]


GROUPS = [
    ('screens', 'Maps and panels', 'Open and close the game screens.',
     ['galaxy_map', 'system_map', 'codex', 'fss_enter', 'left_panel', 'comms_panel', 'radar_panel', 'right_panel',
      'radar_range_up', 'radar_range_down', 'orbit_lines']),
    ('ship', 'Flying the ship', 'The everyday switches and the throttle.',
     ['gear', 'weapons', 'scoop', 'lights', 'night_vision', 'silent_running', 'flight_assist', 'hud_mode', 'head_look',
      'boost', 'speed_0', 'speed_50', 'speed_75', 'speed_100', 'supercruise', 'hyperspace']),
    ('big', 'Big actions', 'She presses a whole run of keys for these. She only acts when she is sure she heard you right, so say them clearly.',
     ['request_docking', 'auto_launch', 'deploy_nomad', 'plot_waypoint', 'show_off']),
    ('combat', 'Combat', 'Targets, power, countermeasures and wingmen.',
     ['next_target', 'prev_target', 'next_hostile', 'prev_hostile', 'highest_threat', 'next_route_system',
      'targets_target', 'next_subsystem', 'prev_subsystem', 'wingman_1', 'wingman_2', 'wingman_3', 'assist_1',
      'assist_2', 'assist_3', 'wing_nav_lock', 'next_fire_group', 'prev_fire_group', 'heatsink', 'shield_cell',
      'chaff', 'ecm', 'power_engines', 'power_weapons', 'power_systems', 'power_reset']),
    ('fighter', 'Ship-launched fighter', 'For ships with a fighter bay.',
     ['fighter_orders', 'fighter_attack', 'fighter_defend', 'fighter_aggressive', 'fighter_hold_fire',
      'fighter_hold_position', 'fighter_follow', 'fighter_recall']),
    ('foot', 'On foot', 'Odyssey: suit, weapons, tools and emotes.', [i for i in C if i.startswith('foot_')]),
    ('overlays', 'Void Compass overlays', 'Only if you run the Void Compass app next to the game.',
     [i for i in C if i.startswith('vc_')]),
]


def say(lst):
    return ''.join('<q>%s</q>' % html.escape(x) for x in lst)


def row(a, b, tag=''):
    return '<tr><td class="cmd">%s%s</td><td class="say">%s</td></tr>' % (html.escape(a), tag, b)


def table(rows):
    return ('<div class="tablewrap"><table><thead><tr><th>What it does</th><th>You can say</th></tr></thead>'
            '<tbody>%s</tbody></table></div>' % ''.join(rows))


sections, used = [], set()
for gid, title, intro, ids in GROUPS:
    rows = []
    for i in ids:
        if i not in C:
            continue
        used.add(i)
        tag = ' <span class="pill">careful</span>' if i in CAREFUL else ''
        rows.append(row(name(C[i]), say(examples(C[i])), tag))
    sections.append((gid, title, intro, table(rows)))
missing = [i for i in C if i not in used]
assert not missing, missing


def simple(rows):
    return table([row(a, say(b)) for a, b in rows])


EXTRA = [
    ('route', 'Routes and navigation',
     'Neutron routes use the free Spansh route plotter, so she needs the internet for these.', [
         ('Plot a neutron route to a system', ['Plot a neutron route to Colonia', 'Plot a route to Sagittarius A star']),
         ('Plot to the destination set in your galaxy map', ['Plot a neutron route']),
         ('Where to next?', ['What is the next waypoint?', 'Where to next?']),
         ('How much is left (with a route plotted)', ['How many jumps are left?', 'Route status']),
         ('Type the next waypoint into the galaxy map for you', ['Plot the next waypoint']),
         ('Start the route again from here', ['Plot it again', 'Recalculate the route']),
         ('Cancel it', ['Cancel the route']),
         ('Lost? A normal course to the nearest point of interest', ['I am lost', 'Emergency protocol', 'Take me to the nearest point of interest']),
         ('Save a place', ['Save this system as bookmark one', 'Set home to here', 'Save this system as my carrier']),
         ('Go to a saved place or your carrier', ['Plot a route to home', 'Take us to my carrier', 'Plot a route to bookmark three']),
         ('Nearest Deep Space Support carrier', ['Plot me a route to the nearest DSSA', 'Plot a route to the nearest DSSA in the Norma Expanse']),
         ('Engineers', ['Take me to Felicity Farseer', 'Where is Lori Jameson?']),
         ('Guardian blueprints', ['Where can I get Guardian weapon blueprints?', 'How do I get Guardian vessel blueprints?']),
         ('Titans', ['Take me to the nearest Titan'])]),
    ('finder', 'Find the nearest service',
     'She searches Spansh for the closest station. If two are close she reads them out as "the first one or the second one". Answer with the one you want and she offers to plot the route.', [
         ('Black market', ['Where is the nearest black market?']),
         ('Material trader', ['Find me a material trader']),
         ('Technology broker', ['Where is the nearest tech broker?']),
         ('Interstellar Factors', ['I need an interstellar factors contact']),
         ('Universal Cartographics', ['Nearest Universal Cartographics']),
         ('Vista Genomics', ['Where is the nearest Vista Genomics?']),
         ('Shipyard and outfitting', ['Where is the nearest shipyard?', 'Find me an outfitting station']),
         ('Redemption office, Pioneer Supplies, Frontline Solutions',
          ['Nearest redemption office', 'Where is Pioneer Supplies?', 'Find Frontline Solutions']),
         ('Bartender', ['Where is the nearest bartender?']),
         ('Answering her offer', ['The first one', 'The second one', 'Yes', 'No'])]),
    ('info', 'Questions about your game', 'She answers from what the game has told her.', [
        ('Where you are', ['Where are we?']),
        ('Your ship', ['What ship am I flying?']),
        ('Ship health', ['Status report', 'How are we doing?']),
        ('Wanted', ['Am I wanted?']),
        ('Time played and your counts',
         ['How long have we been playing?', 'How many jumps have we made?', 'How many kills have I got?',
          'How many terraformable worlds have we found?']),
        ('Places visited', ['How many times have we visited here?']),
        ('Ideas', ['What should we do?', 'What can you do?', "What's new?"]),
        ('Time and date', ["What's the time?", "What's the date?"])]),
    ('chat', 'Chatting with her',
     'She stays in character and her mood changes how she answers.', [
         ('How she is', ['How are you?', 'Do you like me?', 'Do you get lonely?']),
         ('Cheer up', ['Cheer me up', 'Compliment me', 'Roast me']),
         ('Games', ['Flip a coin', 'Roll a dice', 'Pick a number', 'Tell me a riddle']),
         ('Stories and fun', ['Tell me a space joke', 'Tell me a fun fact', 'Tell me a story', 'Write me a poem', 'Tell my fortune']),
         ('Her opinions', ['What is your favourite ship?', 'What do you think about the Thargoids?']),
         ('Talking on', ['Tell me more', 'Why?', 'Say that again', 'What were we talking about?']),
         ('Tell her your plans (she asks when you log in)', ['I think we shall go exploring', 'Maybe some mining today']),
         ('When she asks "Did you mean...?"', ['Yes', 'No'])]),
    ('mining', 'Mining and merits', 'Merit mining needs you to be pledged to a Power. She looks for systems your Power controls that have a pristine metallic ring and a station wanting 2000 tonnes or more, reads out the best two as "the first one or the second one", and offers to plot the route.', [
        ('Go merit mining', ['I want to go merit mining', 'Find me somewhere to merit mine']),
        ('Where to sell', ['Where should I sell the platinum?']),
        ('Where to buy', ['Where can I buy platinum?']),
        ('What you have mined', ['What have we mined?']),
        ('Answering her offer', ['The first one', 'The second one', 'Yes'])]),
    ('facts', 'Facts, sums and conversions', 'She answers these from what she already knows, so no internet is needed. She does not answer anything that changes with the news, such as prices or who is in charge.', [
        ('Facts', ['What is the capital of Spain?', 'How far is the moon?', 'Who was the first man on the moon?']),
        ('Sums', ['What is 12 times 8?']),
        ('Conversions', ['Convert 10 miles to kilometres']),
        ('Time somewhere else', ['What time is it in Australia?'])]),
    ('you', 'Things she learns about you', 'She says out loud whenever she notes something, and keeps it only on your PC. She never keeps anything about health, money, religion, politics or other people.', [
        ('Tell her what you like', ['I love pizza', 'I hate mushrooms']),
        ('Your pets', ['My dog is called Rex']),
        ('Your favourites', ['My favourite colour is blue']),
        ('Ask what she knows', ['What do you know about me?', 'What do you remember?']),
        ('Make her forget', ['Forget that I like pizza', 'Forget what you know about me']),
        ('What she could not answer', ["What couldn't you answer?"])]),
    ('company', 'The East Orion Company', 'Her own story and the squadron she belongs to.', [
        ('The company', ['Tell me about the East Orion Company', 'Tell me more']),
        ('Who runs it', ['Who is the CEO?']),
        ('About her', ['Who are you?', 'Tell me about yourself'])]),
    ('stream', 'For streamers', 'Say these and she talks to your viewers.', [
        ('Greet chat', ['Say hello to chat']),
        ('Thank chat', ['Thank chat for watching']),
        ('Say goodbye', ['Say goodbye to chat']),
        ('Remind them to follow', ['Remind chat to follow']),
        ('Hype them up', ['Hype up chat']),
        ('Show them what she can do', ['Show off'])]),
    ('learn', 'Teaching her your voice', 'Details are in the setup steps above. These work any time. Outside the training, "stop" means all stop (throttle to zero).', [
        ('Start the training', ['Teach me your voice']),
        ('During the training', ['Skip', 'Stop']),
        ('Save what she heard to a file', ['Hearing report']),
        ('Biology overlay', ['Hide the biology overlay', 'Show the biology overlay']),
        ('Viewer chat (Twitch)', ['Pause the chat', 'Chat on']),
        ('Route map overlay', ['Hide the route map', 'Show the route map'])]),
]
for gid, title, intro, rows in EXTRA:
    sections.append((gid, title, intro, simple(rows)))
order = ['route', 'finder', 'mining', 'info', 'facts', 'chat', 'you', 'company', 'stream', 'screens', 'ship', 'big', 'combat', 'fighter', 'foot', 'overlays', 'learn']
secmap = {s[0]: s for s in sections}
sections = [secmap[k] for k in order]
count = sum(t.count('<tr><td') for _, _, _, t in sections)
nav = ''.join('<a href="#%s">%s</a>' % (g, html.escape(t)) for g, t, _, _ in sections)
body = ''.join('<section class="group" id="%s"><h3>%s</h3><p class="intro">%s</p>%s</section>'
               % (g, html.escape(t), html.escape(i), tb) for g, t, i, tb in sections)


def build():
    template = (REPO / "tools" / "guide_template.html").read_text(encoding="utf-8")
    head, _, rest = template.partition('<div class="topnav">')
    page = ('<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n' + head + '</head><body>\n<div class="topnav">' + rest
            + '\n</body></html>\n')
    return page.replace('{{NAV}}', nav).replace('{{COMMANDS}}', body).replace('{{COUNT}}', str(count))


if __name__ == '__main__':
    target = REPO / "site" / "index.html"
    target.parent.mkdir(exist_ok=True)
    target.write_text(build(), encoding="utf-8")
    (REPO / "site" / ".nojekyll").write_text("", encoding="utf-8")
    print("Wrote %s (%d things to say)" % (target, count))
