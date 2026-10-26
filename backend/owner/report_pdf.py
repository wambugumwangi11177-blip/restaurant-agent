"""Printable owner reports built only from the payload displayed by /owner/report."""
from io import BytesIO
from html import escape

def build(report,restaurant_name):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    out=BytesIO()
    doc=SimpleDocTemplate(out,pagesize=(210*mm,297*mm),rightMargin=19*mm,leftMargin=19*mm,topMargin=20*mm,bottomMargin=20*mm)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="LEVIIISmall",fontName="Helvetica",fontSize=9,leading=14,textColor=colors.HexColor("#53645b")))
    styles['Title'].textColor=colors.HexColor("#204638")
    def para(text,style="LEVIIISmall"):
        return Paragraph(escape(str(text or "")).replace("\n","<br/>"),styles[style])
    parts=[para("LEVIII / "+restaurant_name,"Heading2"),para(report['period'].title()+" report","Title"),para(report.get('range','')),Spacer(1,8*mm)]
    if report.get('day_close'):
        parts.append(para('Day close: '+report['day_close']['status'].replace('_',' ')+' / '+report['day_close']['day']))
    for section in report['sections']:
        parts+=[para(section['title'],"Heading2"),para(section.get('window','')),para(section.get('headline') or section.get('reason') or '')]
        rows=section.get('rows') or []
        if not rows and section.get('lines'):
            rows=[{'label':r.get('label',r.get('name','')), 'value':r.get('kes',r.get('amount_kes')), 'unit':'kes'} for r in section['lines']]
        if rows:
            table_rows=[]
            for r in rows:
                value=r.get('value')
                unit=r.get('unit','')
                val='' if value is None else (f"KES {value:,.2f}" if unit=='kes' else f"{value:g}%" if unit=='pct' else str(value))
                table_rows.append([para(r.get('label','')),para(val),para(r.get('note',''))])
            table=Table(table_rows,colWidths=[75*mm,34*mm,61*mm],hAlign='LEFT')
            table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#e2e8e4'))]))
            parts.append(table)
        for a in section.get('assumptions',[]):
            if a.get('text'):parts.append(para('Based on: '+a['text']))
        parts.append(Spacer(1,5*mm))
    parts.append(para('Figures follow the recorded periods and completeness shown in the app. Forecasts are estimates. Tax filing remains with your accountant.'))
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#718077'));canvas.drawString(19*mm,12*mm,'LEVIII / From your restaurant records');canvas.drawRightString(191*mm,12*mm,str(doc.page))
    doc.build(parts,onFirstPage=footer,onLaterPages=footer)
    return out.getvalue()
