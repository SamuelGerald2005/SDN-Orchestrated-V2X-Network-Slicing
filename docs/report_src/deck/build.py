#!/usr/bin/env python3
"""Builds the Evaluation deck from the team's template (unpacked in ./un) using only the standard library.
Keeps template slides 1-5, 7, 9; drops the rest; appends generated slides in the template's visual style."""
import os, re, shutil, struct
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
UN = os.path.join(HERE, 'un')
FIG = os.path.abspath(os.path.join(HERE, '..', '..', 'figures'))
EMU = 914400
MAROON, INK, BODY, MUTED, TINT, GRAYH = 'B90F4B', '141414', '232323', '5A5A5A', 'FBEFF3', 'E6E6E6'
SERIF, SANS, MONO = 'Times New Roman', 'Arial', 'Courier New'
E = lambda v: int(round(v * EMU))


def x(s):
    return escape(s, {'"': '&quot;'})


class Slide:
    def __init__(self, title):
        self.parts, self.nid, self.images = [], 10, []
        self.parts.append(self._title(title))

    def id(self):
        self.nid += 1
        return self.nid

    def _title(self, t):
        return ('<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr>'
                '<a:xfrm><a:off x="502920" y="329184"/><a:ext cx="8600000" cy="438912"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
                '<p:txBody><a:bodyPr wrap="none" lIns="0" tIns="0" rIns="0" bIns="0"><a:spAutoFit/></a:bodyPr><a:lstStyle/><a:p>'
                '<a:r><a:rPr lang="en-US" sz="2500" b="1"><a:solidFill><a:srgbClr val="141414"/></a:solidFill><a:latin typeface="Times New Roman"/></a:rPr>'
                '<a:t>%s</a:t></a:r></a:p></p:txBody></p:sp>'
                '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Title rule"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="502920" y="832104"/><a:ext cx="1828800" cy="41148"/></a:xfrm>'
                '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="B90F4B"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr></p:sp>'
                '<p:pic><p:nvPicPr><p:cNvPr id="4" name="Amrita logo" descr="Amrita Vishwa Vidyapeetham logo"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
                '<p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="9281160" y="155448"/><a:ext cx="2423160" cy="598932"/></a:xfrm>'
                '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>') % x(t)

    @staticmethod
    def run(text, sz=16, b=False, i=False, color=BODY, font=SERIF):
        return ('<a:r><a:rPr lang="en-US" sz="%d"%s%s dirty="0"><a:solidFill><a:srgbClr val="%s"/></a:solidFill>'
                '<a:latin typeface="%s"/><a:cs typeface="%s"/></a:rPr><a:t>%s</a:t></a:r>'
                % (int(sz * 100), ' b="1"' if b else '', ' i="1"' if i else '', color, font, font, x(text)))

    def para(self, runs, align='l', bullet=False, after=6, sz=16):
        ppr = '<a:pPr algn="%s"%s><a:spcAft><a:spcPts val="%d"/></a:spcAft>%s</a:pPr>' % (
            align, ' marL="285750" indent="-285750"' if bullet else '', after * 100,
            '<a:buFont typeface="Arial"/><a:buChar char="&#8226;"/>' if bullet else '<a:buNone/>')
        if isinstance(runs, str):
            runs = [(runs, {})]
        body = ''.join(self.run(t, **dict({'sz': sz}, **o)) for t, o in runs)
        return '<a:p>%s%s</a:p>' % (ppr, body)

    def text(self, xx, yy, w, h, paras, anchor='t', name='Text', inset=0.05):
        n = self.id()
        ins = E(inset)
        self.parts.append(
            '<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s %d"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr>'
            '<a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>'
            '<p:txBody><a:bodyPr wrap="square" lIns="%d" tIns="%d" rIns="%d" bIns="%d" anchor="%s"><a:normAutofit/></a:bodyPr><a:lstStyle/>%s</p:txBody></p:sp>'
            % (n, name, n, E(xx), E(yy), E(w), E(h), ins, ins, ins, ins, anchor, ''.join(paras)))

    def box(self, xx, yy, w, h, fill='FFFFFF', line=MAROON, lw=1.1, round_=True, name='Card', paras=None, anchor='t', inset=0.15):
        n = self.id()
        ln = '<a:ln w="%d"><a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:ln>' % (int(lw * 12700), line) if line else '<a:ln><a:noFill/></a:ln>'
        geom = '<a:prstGeom prst="roundRect"><a:avLst><a:gd name="adj" fmla="val 8000"/></a:avLst></a:prstGeom>' if round_ else '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom>'
        ins = E(inset)
        tx = ''.join(paras) if paras else '<a:p><a:endParaRPr lang="en-US"/></a:p>'
        self.parts.append(
            '<p:sp><p:nvSpPr><p:cNvPr id="%d" name="%s %d"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr>'
            '<a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>%s<a:solidFill><a:srgbClr val="%s"/></a:solidFill>%s</p:spPr>'
            '<p:txBody><a:bodyPr wrap="square" lIns="%d" tIns="%d" rIns="%d" bIns="%d" anchor="%s"><a:normAutofit/></a:bodyPr><a:lstStyle/>%s</p:txBody></p:sp>'
            % (n, name, n, E(xx), E(yy), E(w), E(h), geom, fill, ln, ins, ins, ins, ins, anchor, tx))

    def arrow(self, x1, y1, x2, y2, color=MUTED):
        n = self.id()
        flipH = ' flipH="1"' if x2 < x1 else ''
        flipV = ' flipV="1"' if y2 < y1 else ''
        self.parts.append(
            '<p:cxnSp><p:nvCxnSpPr><p:cNvPr id="%d" name="Arrow %d"/><p:cNvCxnSpPr/><p:nvPr/></p:nvCxnSpPr><p:spPr>'
            '<a:xfrm%s%s><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm><a:prstGeom prst="straightConnector1"><a:avLst/></a:prstGeom>'
            '<a:ln w="19050"><a:solidFill><a:srgbClr val="%s"/></a:solidFill><a:tailEnd type="triangle"/></a:ln></p:spPr></p:cxnSp>'
            % (n, n, flipH, flipV, E(min(x1, x2)), E(min(y1, y2)), E(abs(x2 - x1)), E(abs(y2 - y1)), color))

    def image(self, path, xx, yy, w=None, h=None, descr=''):
        W, H = struct.unpack('>II', open(path, 'rb').read(24)[16:24])
        if w and not h:
            h = w * H / W
        elif h and not w:
            w = h * W / H
        rid = 'rId%d' % (3 + len(self.images))
        self.images.append((rid, path))
        n = self.id()
        self.parts.append(
            '<p:pic><p:nvPicPr><p:cNvPr id="%d" name="Figure %d" descr="%s"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            '<p:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
            '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:ln w="9525"><a:solidFill><a:srgbClr val="D9D9D9"/></a:solidFill></a:ln></p:spPr></p:pic>'
            % (n, n, x(descr), rid, E(xx), E(yy), E(w), E(h)))
        return w, h

    def table(self, xx, yy, colw, rows, rowh=0.42, sz=14, first_col_fills=None, header_fill=GRAYH, aligns=None):
        n = self.id()
        grid = ''.join('<a:gridCol w="%d"/>' % E(c) for c in colw)
        trs = []
        for r, row in enumerate(rows):
            tcs = []
            for c, cell in enumerate(row):
                hdr = r == 0
                fill = header_fill if hdr else ((first_col_fills or {}).get(r, 'FFFFFF') if c == 0 else 'FFFFFF')
                al = 'ctr' if hdr else ((aligns or ['l'] * len(row))[c])
                bold = hdr or c == 0
                tcs.append('<a:tc><a:txBody><a:bodyPr/><a:lstStyle/><a:p><a:pPr algn="%s"/>%s</a:p></a:txBody>'
                           '<a:tcPr marL="73152" marR="73152" marT="45720" marB="45720" anchor="ctr">'
                           '<a:lnL w="9525"><a:solidFill><a:srgbClr val="BFBFBF"/></a:solidFill></a:lnL><a:lnR w="9525"><a:solidFill><a:srgbClr val="BFBFBF"/></a:solidFill></a:lnR>'
                           '<a:lnT w="9525"><a:solidFill><a:srgbClr val="BFBFBF"/></a:solidFill></a:lnT><a:lnB w="9525"><a:solidFill><a:srgbClr val="BFBFBF"/></a:solidFill></a:lnB>'
                           '<a:solidFill><a:srgbClr val="%s"/></a:solidFill></a:tcPr></a:tc>'
                           % (al, self.run(cell, sz=sz, b=bold, color='000000', font=SANS), fill))
            trs.append('<a:tr h="%d">%s</a:tr>' % (E(rowh), ''.join(tcs)))
        self.parts.append(
            '<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="%d" name="Table %d"/><p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr><p:nvPr/></p:nvGraphicFramePr>'
            '<p:xfrm><a:off x="%d" y="%d"/><a:ext cx="%d" cy="%d"/></p:xfrm><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/table">'
            '<a:tbl><a:tblPr firstRow="1" bandRow="1"/><a:tblGrid>%s</a:tblGrid>%s</a:tbl></a:graphicData></a:graphic></p:graphicFrame>'
            % (n, n, E(xx), E(yy), E(sum(colw)), E(rowh * len(rows)), grid, ''.join(trs)))

    def xml(self):
        return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
                'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
                '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>%s</p:spTree></p:cSld>'
                '<p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>' % ''.join(self.parts))


# ------------------------------------------------------------------ helpers for repeated patterns
def card(s, xx, yy, w, h, head, body, head_sz=18, body_sz=15, fill='FFFFFF', line=MAROON):
    paras = [s.para([(head, {'b': True, 'color': MAROON, 'sz': head_sz})], after=4)]
    for b in (body if isinstance(body, list) else [body]):
        paras.append(s.para(b if isinstance(b, list) else [(b, {})], sz=body_sz, after=4))
    s.box(xx, yy, w, h, fill=fill, line=line, paras=paras)


def stat(s, xx, yy, w, h, big, label, big_sz=40, fill=MAROON, ink='FFFFFF', sub_ink='F6D9E3'):
    s.box(xx, yy, w, h, fill=fill, line=None, anchor='ctr', paras=[
        s.para([(big, {'b': True, 'color': ink, 'sz': big_sz})], align='ctr', after=2),
        s.para([(label, {'color': sub_ink, 'sz': 14})], align='ctr', after=0)])


def bullets(s, items, sz=16, after=8):
    out = []
    for it in items:
        if isinstance(it, str):
            it = [(it, {})]
        out.append(s.para(it, bullet=True, sz=sz, after=after))
    return out


L, R, TOP = 0.55, 12.78, 1.15     # content box (inches)
slides = []

# ------------------------------------------------------------------ 6. what we built
s = Slide('WHAT WE BUILT')
s.text(L, TOP, 8.1, 0.55, [s.para([('An SDN orchestrator (a RYU application) that runs five V2X slices on an emulated network of 6 vehicles, 2 RSUs with edge servers and a 20 Mb/s backhaul.', {'sz': 16})])])
cw, ch, g = 3.95, 2.3, 0.25
cards = [('1. Isolation', 'Each slice has its own OpenFlow meter. Traffic above the slice budget is dropped, so no slice can take another’s bandwidth.'),
         ('2. Priority', 'The controller writes a DSCP mark. Strict-priority queues on the backhaul always send URLLC and platoon packets first.'),
         ('3. Dynamic reallocation', 'Every 2 s the orchestrator reads the meter counters and shrinks eMBB to what the critical slices leave free. A REST API resizes slices live.'),
         ('4. Mobility', 'Handovers are detected and stale rules flushed on every switch, so traffic follows the vehicle. Scripted paths and random waypoint.')]
for k, (h, b) in enumerate(cards):
    card(s, L + (k % 2) * (cw + g), 1.95 + (k // 2) * (ch + g), cw, ch, h, b)
sx = L + 2 * cw + g + 0.4
stat(s, sx, 1.95, R - sx, ch, '3.8 s → 25 ms', 'platoon delay (p95) during an eMBB flood: best effort vs orchestrator', big_sz=32)
stat(s, sx, 1.95 + ch + g, R - sx, ch, '0 % loss', 'for every critical slice under congestion, against 7.7 to 9.8 % without slicing', big_sz=32, fill='F2F2F2', ink=MAROON, sub_ink=BODY)
slides.append(s)

# ------------------------------------------------------------------ 8. architecture
s = Slide('SYSTEM ARCHITECTURE & PACKET PIPELINE')
w, h = s.image(os.path.join(FIG, 'architecture.png'), 0, 1.1, h=5.65, descr='Testbed topology and the five steps every switch applies to a packet')
s.parts[-1] = s.parts[-1].replace('<a:off x="0"', '<a:off x="%d"' % E((13.333 - w) / 2), 1)
slides.append(s)

# ------------------------------------------------------------------ 10. slices
s = Slide('SLICE CONFIGURATION')
rows = [['Slice', 'V2X function', 'Match', 'Meter, budget', 'DSCP', 'Backhaul band', 'Destination'],
        ['URLLC', 'Safety / collision alerts', 'UDP 5000', '1, 5 Mb/s', '46 (EF)', '1 (highest)', 'Edge MEC'],
        ['Platoon', 'Cooperative driving (V2V)', 'UDP 9000', '2, 4 Mb/s', '40 (CS5)', '1 (highest)', 'Other vehicle'],
        ['eMBB', 'Infotainment / video', 'TCP 8080', '3, 12 Mb/s, set by the loop', '10 (AF11)', '3 (lowest)', 'Central infotain'],
        ['mMTC', 'Telemetry / diagnostics', 'UDP 1883', '4, 1 Mb/s', '18 (AF21)', '2', 'Central telemetry'],
        ['Best effort', 'Everything else', 'any', '5, 2 Mb/s', '0', '3 (lowest)', 'any']]
s.table(L, TOP + 0.1, [1.55, 2.6, 1.3, 2.45, 1.25, 1.55, 1.53], rows, rowh=0.55, sz=14,
        first_col_fills={1: 'E4EEFA', 2: 'FCE8DE', 3: 'DDF3EA', 4: 'FDF1D6', 5: 'F2F2F2'})
s.box(L, 4.75, R - L, 1.55, fill=TINT, line=None, paras=[
    s.para([('Correction from Evaluation I', {'b': True, 'color': MAROON, 'sz': 17})], after=4),
    s.para([('Slices are not mapped to OVS queues 0–3, and URLLC is not “Queue 0”. Each slice is policed by an OpenFlow meter; the DSCP mark selects one of three strict-priority bands on the backhaul links. Rules match both directions (destination and source port), so replies are classified too.', {'sz': 15})], after=0)])
slides.append(s)

# ------------------------------------------------------------------ 11. enforcement
s = Slide('ENFORCEMENT: METERS & PRIORITY QUEUES')
s.text(L, TOP, 6.0, 0.4, [s.para([('Queue tree on both ends of each backhaul link', {'b': True, 'color': MAROON, 'sz': 17})])])
bx = L
s.box(bx, 1.7, 5.6, 0.62, fill='F2F2F2', line='BFBFBF', anchor='ctr', paras=[s.para([('HTB 20 Mb/s', {'b': True, 'sz': 15}), ('  (the link rate)', {'sz': 15})], align='ctr', after=0)], inset=0.05)
s.arrow(bx + 2.8, 2.32, bx + 2.8, 2.62)
s.box(bx, 2.62, 5.6, 0.62, fill='F2F2F2', line='BFBFBF', anchor='ctr', paras=[s.para([('prio, 3 bands', {'b': True, 'sz': 15}), ('  band 1 always goes first', {'sz': 15})], align='ctr', after=0)], inset=0.05)
bands = [('Band 1', 'URLLC, platoon', 'DSCP 46, 40', 'FCE4EC'), ('Band 2', 'mMTC', 'DSCP 18', 'FDF1D6'), ('Band 3', 'eMBB, best effort', 'other', 'F2F2F2')]
bw = (5.6 - 2 * 0.2) / 3
for k, (n_, who, d, f) in enumerate(bands):
    xx = bx + k * (bw + 0.2)
    s.arrow(bx + 2.8, 3.24, xx + bw / 2, 3.55)
    s.box(xx, 3.55, bw, 1.25, fill=f, line='BFBFBF', anchor='ctr', inset=0.06, paras=[
        s.para([(n_, {'b': True, 'sz': 15, 'color': MAROON})], align='ctr', after=2),
        s.para([(who, {'sz': 14})], align='ctr', after=2), s.para([(d, {'sz': 13, 'color': MUTED})], align='ctr', after=0)])
    s.box(xx, 5.0, bw, 0.5, fill='FFFFFF', line='BFBFBF', anchor='ctr', inset=0.04, paras=[s.para([('netem 5 ms', {'sz': 13})], align='ctr', after=0)])
s.text(bx, 5.65, 5.6, 0.9, [s.para([('Packet counters: in a heavy-load trial ', {'sz': 14}), ('61 MB', {'sz': 14, 'b': True}), (' went through band 1 with marking on, and ', {'sz': 14}), ('0 bytes', {'sz': 14, 'b': True}), (' with it off.', {'sz': 14})])])
tx = 6.75
s.text(tx, TOP, R - tx, 0.4, [s.para([('Meters measured (functional tests)', {'b': True, 'color': MAROON, 'sz': 17})])])
s.table(tx, 1.7, [2.35, 1.2, 1.3, 1.18], [
    ['Test', 'Offered', 'Delivered', 'Limit'],
    ['URLLC flood', '10 Mb/s', '4.96 Mb/s', '5 Mb/s'],
    ['mMTC flood', '2 Mb/s', '0.99 Mb/s', '1 Mb/s'],
    ['Best-effort flood', '4 Mb/s', '1.97 Mb/s', '2 Mb/s'],
    ['eMBB TCP download', 'unlimited', '11.3 Mb/s', '12 Mb/s'],
    ['REST: URLLC set to 3 Mb/s', '10 Mb/s', '2.98 Mb/s', '3 Mb/s']], rowh=0.5, sz=14, aligns=['l', 'r', 'r', 'r'])
s.box(tx, 4.95, R - tx, 1.45, fill=TINT, line=None, paras=[
    s.para([('Why both?', {'b': True, 'color': MAROON, 'sz': 16})], after=3),
    s.para([('Meters stop a slice taking more than its share. Priority decides who waits when the link is full anyway: the budgets add up to 24 Mb/s on a 20 Mb/s link.', {'sz': 14})], after=0)])
slides.append(s)

# ------------------------------------------------------------------ 12. capacity loop
s = Slide('DYNAMIC REALLOCATION: THE CAPACITY LOOP')
s.box(L, TOP + 0.05, R - L, 1.05, fill=TINT, line=None, anchor='ctr', paras=[
    s.para([('Every 2 s, per switch:  ', {'b': True, 'sz': 18, 'color': MAROON}),
            ('eMBB budget = 20 Mb/s − critical load − 1.5 Mb/s headroom', {'sz': 18, 'b': True})], align='ctr', after=3),
    s.para([('critical load = measured URLLC + platoon rate;  500 kb/s steps;  never below 2 Mb/s', {'sz': 15, 'color': MUTED})], align='ctr', after=0)])
s.text(L, 2.5, 8, 0.4, [s.para([('What happened in every heavy-load trial (all three switches)', {'b': True, 'sz': 16})])])
ev = [('PROTECT_ON', 'critical 7.9 Mb/s', 'eMBB 12 → 10.5 Mb/s'), ('ADJUST', 'critical 8.6 Mb/s', 'eMBB → 9.5 Mb/s'), ('PROTECT_OFF', 'critical 0.6 Mb/s', 'eMBB back to 12 Mb/s')]
ew = 3.6
for k, (n_, a, b) in enumerate(ev):
    xx = L + k * (ew + 0.6)
    s.box(xx, 3.0, ew, 1.5, fill='FFFFFF', line=MAROON, anchor='ctr', paras=[
        s.para([(n_, {'b': True, 'sz': 18, 'color': MAROON, 'font': SANS})], align='ctr', after=4),
        s.para([(a, {'sz': 15})], align='ctr', after=2), s.para([(b, {'sz': 15, 'b': True})], align='ctr', after=0)])
    if k < 2:
        s.arrow(xx + ew + 0.08, 3.75, xx + ew + 0.52, 3.75)
s.text(L, 4.75, 5.9, 0.4, [s.para([('Manual control: REST API on port 8081', {'b': True, 'sz': 16})])])
s.box(L, 5.2, 6.3, 1.25, fill='F2F2F2', line=None, inset=0.12, paras=[
    s.para([('GET  /v2x/slices', {'font': MONO, 'sz': 14})], after=2),
    s.para([('PUT  /v2x/slices/urllc  {"kbps": 3000}', {'font': MONO, 'sz': 14})], after=2),
    s.para([('GET  /v2x/events', {'font': MONO, 'sz': 14})], after=0)])
s.text(7.15, 4.75, R - 7.15, 1.75, bullets(s, ['The PUT changed the meter at once: the URLLC flow fell to 2.98 Mb/s, then was restored to 5 Mb/s',
                                                  'Bad requests are rejected: 404 for an unknown slice, 400 for a malformed body'], sz=15, after=6))
slides.append(s)

# ------------------------------------------------------------------ 13. mobility
s = Slide('MOBILITY: PROBLEMS FOUND AND FIXED')
mob = [('Cross-RSU V2V failed after moving', 'Only 74/90 pings. The old RSU kept a departed vehicle in its station list and delivered its frames locally.',
        'RSU settings from Saraiva et al. (ap_max_inactivity 6 s) and a 1 s beacon from each vehicle.', '90/90, three times in a row'),
       ('Same-RSU traffic skipped its meter', 'The access point bridged two of its own vehicles itself, so the frames never reached OpenFlow.',
        'Client isolation on the RSUs; the controller sends that traffic back out the same Wi-Fi port.', 'Now counted and limited by the platoon meter'),
       ('Coverage hole between RSUs', 'Vehicles in the middle of the road were out of range of both RSUs.',
        'RSU range set to 30 m (13 dBm). Random-waypoint mobility added, seeded so runs repeat.', 'Both mobility modes used in the experiments')]
mw = (R - L - 2 * 0.3) / 3
for k, (h_, prob, fix, res) in enumerate(mob):
    xx = L + k * (mw + 0.3)
    s.box(xx, TOP + 0.1, mw, 4.3, fill='FFFFFF', line=MAROON, paras=[
        s.para([(h_, {'b': True, 'color': MAROON, 'sz': 18})], after=8),
        s.para([('Cause: ', {'b': True, 'sz': 15}), (prob, {'sz': 15})], after=8),
        s.para([('Fix: ', {'b': True, 'sz': 15}), (fix, {'sz': 15})], after=0)])
    s.box(xx + 0.15, TOP + 3.55, mw - 0.3, 0.7, fill=TINT, line=None, anchor='ctr', inset=0.08, paras=[s.para([(res, {'b': True, 'sz': 14})], align='ctr', after=0)])
s.box(L, 5.8, R - L, 0.7, fill='F2F2F2', line=None, anchor='ctr', paras=[s.para([
    ('Handover detection: ', {'b': True, 'sz': 15}), ('when a vehicle’s address appears behind a new port, its forwarding rules are deleted on every switch and relearned on the new path.', {'sz': 15})], after=0)])
slides.append(s)

# ------------------------------------------------------------------ 14. latency
s = Slide('EDGE VS CENTRAL LATENCY')
s.text(L, TOP, R - L, 0.5, [s.para([('Round-trip time from a vehicle with the network idle. Safety traffic goes to the edge server of the vehicle’s own RSU.', {'sz': 16})])])
tiles = [('1.2 ms', 'to the MEC server of the vehicle’s own RSU', MAROON, 'FFFFFF', 'F6D9E3'),
         ('21 ms', 'to the other RSU’s MEC (crosses the backhaul twice)', 'F2F2F2', MAROON, BODY),
         ('40.7 ms', 'to the central infotainment and telemetry servers', 'F2F2F2', MAROON, BODY)]
tw = (R - L - 2 * 0.35) / 3
for k, (b, l, f, ink, sub) in enumerate(tiles):
    stat(s, L + k * (tw + 0.35), 2.0, tw, 2.4, b, l, big_sz=48, fill=f, ink=ink, sub_ink=sub)
s.text(L, 4.75, R - L, 1.6, bullets(s, ['The edge path never touches the congested backhaul, so it stays near 1–2 ms even during the eMBB flood (4.7 ms at p95)',
                                        'Link model: RSU–MEC 0.5 ms; RSU–s1 20 Mb/s, 5 ms; s1–central servers 100 Mb/s, 15 ms'], sz=16))
slides.append(s)

# ------------------------------------------------------------------ 15. experiment design
s = Slide('EXPERIMENT DESIGN')
s.text(L, TOP, 6.2, 0.4, [s.para([('Five setups, each adding one mechanism', {'b': True, 'color': MAROON, 'sz': 17})])])
Y = '✔'
s.table(L, 1.65, [2.2, 1.25, 1.55, 1.4], [['Setup', 'Meters', 'Priority', 'Loop'],
                                         ['Best effort', '–', '–', '–'], ['Meters only', Y, '–', '–'],
                                         ['Meters + loop', Y, '–', Y], ['Static slicing', Y, Y, '–'], ['Orchestrated', Y, Y, Y]],
        rowh=0.5, sz=15, aligns=['l', 'ctr', 'ctr', 'ctr'], first_col_fills={5: TINT})
s.text(L, 4.85, 6.4, 1.6, bullets(s, ['Each trial starts from a clean testbed and lasts about 2 minutes',
                                      '4 UDP probes at 100 packets/s record every packet’s round trip; a 30 s, 4-stream TCP download floods the backhaul',
                                      '5 repeats of everything: 80 trials'], sz=15, after=5))
sx = 7.35
s.text(sx, TOP, R - sx, 0.4, [s.para([('Four scenarios', {'b': True, 'color': MAROON, 'sz': 17})])])
sc = [('Congestion', 'Parked vehicles, light critical traffic, then the eMBB flood'),
      ('Heavy', 'Critical flows raised to 4.3 and 3.5 Mb/s, so the link really overflows'),
      ('Handover', 'Vehicles drive between the RSUs while the flows run'),
      ('Random', 'Random-waypoint mobility plus the eMBB flood')]
for k, (h_, b) in enumerate(sc):
    s.box(sx, 1.65 + k * 1.2, R - sx, 1.05, fill='FFFFFF', line=MAROON, anchor='ctr', inset=0.12, paras=[
        s.para([(h_, {'b': True, 'color': MAROON, 'sz': 16}), ('   ' + b, {'sz': 15})], after=0)])
slides.append(s)


# ------------------------------------------------------------------ result slides
def result(title, fig, descr, stat_big, stat_lbl, pts, fig_h=5.55):
    s = Slide(title)
    w, h = s.image(os.path.join(FIG, fig), L, TOP, h=fig_h, descr=descr)
    rx = L + w + 0.35
    stat(s, rx, TOP, R - rx, 1.55, stat_big, stat_lbl, big_sz=30)
    s.text(rx, TOP + 1.75, R - rx, fig_h - 1.75, bullets(s, pts, sz=15, after=7))
    return s


slides.append(result('RESULTS: CONGESTION', 'congestion_load_rtt_p95.png', '95th percentile RTT per flow and setup during the eMBB flood, congestion scenario',
                     '3.8 s → 24.9 ms', 'platoon p95, best effort vs orchestrated',
                     ['Without slicing, eMBB fills the backhaul queue: platoon and mMTC lose 7.7 % and 9.8 % of packets',
                      'Any slicing setup caps eMBB (16.9 → 11.3 Mb/s), so the link never overflows: 0 % loss',
                      'Priority shaves a little more: jitter 1.5 ms against 1.7 ms',
                      'Mean of 5 repeats; whiskers show one standard deviation (under 1 %)']))
slides.append(result('RESULTS: HEAVY CRITICAL LOAD', 'heavy_load_rtt_p95.png', '95th percentile RTT and eMBB throughput, heavy critical load scenario',
                     '203 ms → 23 ms', 'platoon p95, meters only vs full system',
                     ['Budgets add up to 24 Mb/s on a 20 Mb/s link, so meters alone let it overflow: 203 ms',
                      [('Loop', {'b': True}), (' shrinks eMBB to 8.9 Mb/s: 24.4 ms', {})],
                      [('Priority', {'b': True}), (' lets critical packets skip the queue: 23.3 ms, eMBB keeps 11.2 Mb/s', {})],
                      [('Both', {'b': True}), (': 23.2 ms, the lowest delay and jitter', {})]]))

s = Slide('ONE RUN, SECOND BY SECOND')
w, h = s.image(os.path.join(FIG, 'timeline_scripted_best_effort_vs_orchestrated.png'), L, TOP, h=5.55, descr='Per-second RTT of four flows over a 100 s run, best effort above, orchestrated below')
rx = L + w + 0.35
s.text(rx, TOP, R - rx, 5.55, [
    s.para([('Same vehicles, paths and flood', {'b': True, 'color': MAROON, 'sz': 17})], after=10)] + bullets(s, [
        [('0–16 s: ', {'b': True}), ('vehicles drive through the handovers; identical in both runs', {})],
        [('30–70 s: ', {'b': True}), ('eMBB flood (green band)', {})],
        [('Best effort: ', {'b': True}), ('platoon and URLLC climb towards 1 s', {})],
        [('Orchestrated: ', {'b': True}), ('flat at about 22 ms throughout', {})],
        'This is the dashboard recording shown in the demo'], sz=15, after=8))
slides.append(s)

s = Slide('RESULTS: HANDOVER & RANDOM MOBILITY')
w, h = s.image(os.path.join(FIG, 'handover_moving_loss_pct.png'), L, TOP, w=8.3, descr='Packet loss while vehicles move, per flow and setup')
rx = L + 8.3 + 0.35
stat(s, rx, TOP, R - rx, 1.45, '82 % → 50 %', 'platoon loss while moving, best effort vs orchestrated', big_sz=30)
stat(s, rx, TOP + 1.65, R - rx, 1.45, '47 % → 22 %', 'platoon loss under random waypoint (wide spread)', big_sz=30, fill='F2F2F2', ink=MAROON, sub_ink=BODY)
s.box(L, TOP + h + 0.3, R - L, 6.5 - (TOP + h + 0.3), fill=TINT, line=None, paras=[
    s.para([('Limitation: a 7–14 s gap at every handover, in every setup', {'b': True, 'color': MAROON, 'sz': 17})], after=5)] + bullets(s, [
        'Mininet-WiFi reports the new association within a second, but the first packet reaches the new RSU’s switch 6–10 s later',
        'The emulated station re-associates slowly between RSUs on channels 1 and 6, before any packet reaches OpenFlow, so the controller cannot shorten it',
        'Slicing still halves the loss around it, because the moving vehicles’ traffic no longer waits behind eMBB'], sz=15, after=4))
slides.append(s)

# ------------------------------------------------------------------ dashboard
s = Slide('DASHBOARD')
s.text(L, TOP, R - L, 0.5, [s.para([('A web dashboard (python3 dashboard/server.py, port 8090) replays recorded runs or follows the live testbed. No sudo or Docker needed for replays.', {'sz': 16})])])
tabs = [('Run', ['Map: RSU ranges, backhaul, MEC servers, the six vehicles moving, handover rings',
                 'Tiles: worst URLLC delay, platoon loss, eMBB at s1, orchestrator state',
                 'RTT per flow, with a second recording to compare against',
                 'Slice throughput and eMBB limit per switch; controller events']),
        ('Experiment results', ['All 80 trials, by scenario, window and measure',
                                'Bars with standard deviation, plus a table view']),
        ('How it works', ['Architecture, slices, the packet path, the loop and the five setups',
                          'Used to open the demo'])]
tw = (R - L - 2 * 0.3) / 3
for k, (h_, pts) in enumerate(tabs):
    xx = L + k * (tw + 0.3)
    s.box(xx, 1.9, tw, 3.4, fill='FFFFFF', line=MAROON, paras=[s.para([(h_ + ' tab', {'b': True, 'color': MAROON, 'sz': 18})], after=6)] + bullets(s, pts, sz=14, after=5))
s.box(L, 5.55, R - L, 0.95, fill='F2F2F2', line=None, anchor='ctr', paras=[
    s.para([('Live mode: ', {'b': True, 'sz': 15}), ('sudo bash scripts/run_live_demo_host.sh orchestrated 30', {'font': MONO, 'sz': 14}),
            (', then pick “Live testbed”. Links open a chosen moment, e.g. ', {'sz': 15}), ('?rec=scripted_best_effort&cmp=scripted_orchestrated&t=55', {'font': MONO, 'sz': 13})], after=0)])
slides.append(s)

# ------------------------------------------------------------------ summary
s = Slide('SUMMARY OF CONTRIBUTIONS')
contrib = ['OpenFlow 1.3 orchestrator: 5 V2X slices, each policed by a meter and marked for strict-priority backhaul queues',
           'Capacity-aware loop that reallocates eMBB every 2 s from measured meter counters, plus a REST API for slice resizing',
           'Mobility-aware forwarding with handover detection, and RSU settings that make cross-RSU traffic reliable',
           'Reproducible benchmark (5 setups × 4 scenarios × 5 repeats) and a dashboard that shows it working']
s.text(L, TOP + 0.05, 6.6, 5.3, [s.para([('%d. ' % (k + 1), {'b': True, 'color': MAROON, 'sz': 17}), (c, {'sz': 16})], after=14) for k, c in enumerate(contrib)])
gx, gw, gh = 7.55, 2.5, 2.45
st = [('150×', 'lower platoon delay under congestion'), ('500×', 'lower URLLC delay to the edge'),
      ('203 → 23 ms', 'heavy load: meters only vs full system'), ('< 1 %', 'spread across 5 repeats (parked scenarios)')]
for k, (b, l) in enumerate(st):
    xx, yy = gx + (k % 2) * (gw + 0.23), TOP + 0.05 + (k // 2) * (gh + 0.25)
    stat(s, xx, yy, gw, gh, b, l, big_sz=34 if len(b) < 8 else 24, fill=MAROON if k in (0, 3) else 'F2F2F2',
         ink='FFFFFF' if k in (0, 3) else MAROON, sub_ink='F6D9E3' if k in (0, 3) else BODY)
slides.append(s)

# ------------------------------------------------------------------ milestones
s = Slide('MILESTONES & PROJECT TIMELINE')
D = '✅ Done'
s.table(L + 0.5, TOP + 0.1, [6.6, 2.7, 1.9], [
    ['Sub-task', 'Planned date', 'Status'],
    ['1. Literature survey & requirements', 'Sat, 01 Aug 2026', D], ['2. Network topology design', 'Sun, 09 Aug 2026', D],
    ['3. Vehicle mobility modelling', 'Tue, 25 Aug 2026', D], ['4. RYU controller development', 'Tue, 01 Sep 2026', D],
    ['5. Traffic generation pipeline', 'Sat, 26 Sep 2026', D], ['6. QoS & slice enforcement (meters, priority queues)', 'Sat, 03 Oct 2026', D],
    ['7. Dynamic orchestration module', 'Sat, 10 Oct 2026', D], ['8. Performance evaluation & report', 'Sat, 17 Oct 2026', D],
    ['9. Dashboard, 80-trial benchmark & analysis', 'Fri, 06 Nov 2026', D]], rowh=0.52, sz=15, aligns=['l', 'l', 'l'])
slides.append(s)

# ------------------------------------------------------------------ future work
s = Slide('LIMITATIONS & FUTURE WORK')
fw = [('Shorten the handover gap', 'Both RSUs on one channel, faster station scanning, then re-measure mobility'),
      ('Nearest-MEC steering', 'After a handover, redirect safety traffic to the new RSU’s edge server'),
      ('Road-constrained mobility', 'Drive the vehicles from a SUMO road network instead of scripted paths'),
      ('Scale out', 'More vehicles and RSUs, to show the controller and the loop scale'),
      ('Smarter loop input', 'Count critical traffic after policing, so a misbehaving flow cannot shrink eMBB')]
fwd = (R - L - 0.3) / 2
for k, (h_, b) in enumerate(fw):
    xx, yy = L + (k % 2) * (fwd + 0.3), TOP + 0.1 + (k // 2) * 1.75
    card(s, xx, yy, fwd, 1.5, h_, b, head_sz=17, body_sz=15)
xx, yy = L + fwd + 0.3, TOP + 0.1 + 2 * 1.75
s.box(xx, yy, fwd, 1.5, fill=TINT, line=None, paras=[
    s.para([('Emulation, not hardware', {'b': True, 'color': MAROON, 'sz': 17})], after=4),
    s.para([('Radio behaviour comes from Mininet-WiFi; we claim comparisons between setups on the same host, not absolute numbers.', {'sz': 15})], after=0)])
slides.append(s)

# ------------------------------------------------------------------ references
s = Slide('REFERENCES')
refs = ['Alhilal, A., Braud, T., & Hui, P. — Distributed Vehicular Computing at the Dawn of 5G: A Survey, arXiv:2001.07077.',
        'Campolo, C., Fontes, R. R., et al. — Slicing on the Road: Enabling Automotive Verticals through 5G Softwarization, Sensors 18(12):4435, 2018.',
        'Fontes, R. R., Afzal, S., et al. — Mininet-WiFi: Emulating Software-Defined Wireless Networks, IEEE CNSM, 2015.',
        'Slicing 5G Core Network Based on the Ryu SDN Controller for XaaS — MDPI / ResearchGate.',
        'QoS-Driven Slicing Management for Vehicular Communications — MDPI Electronics 13(2):314, 2024.',
        'Network Slice Allocation for 5G V2X Networks: Implementation & Assessment — Elsevier ScienceDirect case study.',
        'Saraiva, T. et al. — An Application-Driven Framework for Intelligent Transportation Systems Using SDN, IEEE T-ITS 22(8), 2021.',
        'Shah, et al. — safety-slice prioritisation during mobility with a DRL xApp, IEEE Trans. Consumer Electronics 71(1), 2025.',
        'Ahmad, Gul & Derawi — four-slice priority-weighted dynamic bandwidth allocation, Sensors 26(13), 2026.']
s.text(L, TOP + 0.05, R - L, 5.4, [s.para([('%d. ' % (k + 1), {'sz': 15, 'b': True}), (r, {'sz': 15})], after=9) for k, r in enumerate(refs)])
slides.append(s)

# ------------------------------------------------------------------ thank you
s = Slide('THANK YOU')
s.box(2.4, 2.3, 8.5, 2.6, fill=MAROON, line=None, anchor='ctr', paras=[
    s.para([('Questions?', {'b': True, 'sz': 40, 'color': 'FFFFFF'})], align='ctr', after=10),
    s.para([('Live dashboard demo: http://127.0.0.1:8090', {'sz': 18, 'color': 'F6D9E3'})], align='ctr', after=4),
    s.para([('A. Adharsh  ·  Rishabh Bhat  ·  Samuel Gerald', {'sz': 18, 'color': 'FFFFFF'})], align='ctr', after=0)])
slides.append(s)


# ------------------------------------------------------------------ assemble
def main():
    pres_p = os.path.join(UN, 'ppt', 'presentation.xml')
    rels_p = os.path.join(UN, 'ppt', '_rels', 'presentation.xml.rels')
    ct_p = os.path.join(UN, '[Content_Types].xml')
    pres, rels, ct = open(pres_p).read(), open(rels_p).read(), open(ct_p).read()
    # map slide file -> rId
    rid_of = {m.group(2): m.group(1) for m in re.finditer(r'<Relationship Id="(rId\d+)" Type="[^"]*/slide" Target="slides/(slide\d+\.xml)"', rels)}
    if not rid_of:
        rid_of = {m.group(2): m.group(1) for m in re.finditer(r'Id="(rId\d+)"[^>]*Target="slides/(slide\d+\.xml)"', rels)}
    sld = dict(re.findall(r'<p:sldId id="(\d+)" r:id="(rId\d+)"/>', pres))
    id_of_rid = {v: k for k, v in sld.items()}
    # final order: template slides then generated ones at the right places
    order = [('t', 1), ('t', 2), ('t', 3), ('t', 4), ('t', 5), ('g', 0), ('t', 7), ('g', 1), ('t', 9)] + [('g', k) for k in range(2, len(slides))]
    next_id = max(int(k) for k in sld) + 1
    next_rid = max(int(r[3:]) for r in re.findall(r'Id="(rId\d+)"', rels)) + 1
    os.makedirs(os.path.join(UN, 'ppt', 'media'), exist_ok=True)
    entries, media_n = [], 0
    for kind, k in order:
        if kind == 't':
            rid = rid_of['slide%d.xml' % k]
            entries.append('<p:sldId id="%s" r:id="%s"/>' % (id_of_rid[rid], rid))
            continue
        sl = slides[k]
        name = 'slide%d.xml' % (100 + k)
        open(os.path.join(UN, 'ppt', 'slides', name), 'w').write(sl.xml())
        srels = ['<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout7.xml"/>',
                 '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image1.png"/>']
        for rid_img, path in sl.images:
            media_n += 1
            mname = 'gen_fig%d.png' % media_n
            shutil.copy(path, os.path.join(UN, 'ppt', 'media', mname))
            srels.append('<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/%s"/>' % (rid_img, mname))
        open(os.path.join(UN, 'ppt', 'slides', '_rels', name + '.rels'), 'w').write(
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>' % ''.join(srels))
        rid = 'rId%d' % next_rid; next_rid += 1
        rels = rels.replace('</Relationships>', '<Relationship Id="%s" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/%s"/></Relationships>' % (rid, name))
        ct = ct.replace('</Types>', '<Override PartName="/ppt/slides/%s" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>' % name)
        entries.append('<p:sldId id="%d" r:id="%s"/>' % (next_id, rid)); next_id += 1
    pres = re.sub(r'<p:sldIdLst>.*?</p:sldIdLst>', '<p:sldIdLst>%s</p:sldIdLst>' % ''.join(entries), pres, flags=re.S)
    open(pres_p, 'w').write(pres); open(rels_p, 'w').write(rels); open(ct_p, 'w').write(ct)
    print('slides in deck:', len(entries))


if __name__ == '__main__':
    main()
