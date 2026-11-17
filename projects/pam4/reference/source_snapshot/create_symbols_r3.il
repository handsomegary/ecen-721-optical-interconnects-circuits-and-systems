; Project 6 native symbol helper. Only creates the absent r3 core symbol view.
; Run with the new project's exact -cdslib, LA_PROJECT_DIR and LA_OA_RUN_DIR.
;
; API references checked in installed official Cadence IC6.1.8 documentation:
; /opt/eda/cadence/IC618/doc/skcompref/chap2.html
;   schCreateSymbolPin(cv master name direction origin orientation [flatten ...])
;   schCreateSymbolShape(cv shape style points [width])
;   schCreateSymbolLabel(cv point choice text justify orient font height type)
; schCreatePin is documented for schematic views only and is NOT used here.
; basic/sympin was confirmed present in the installed basic library.
; No PDK models, CDF, schematic circuitry, or existing symbol views are changed.

procedure(p6SymbolSpecs()
  let((core sampler lane y)
    ; Pin rows: name, expected direction, position x/y, rectangle edge side.
    core=list(
      list("inp" "input" -0.25 2.25 "left")
      list("inn" "input" -0.25 1.75 "left")
      list("vb" "input" -0.25 0.75 "left")
      list("outp" "output" 5.25 2.25 "right")
      list("outn" "output" 5.25 1.75 "right")
      list("vdd" "inputOutput" 2.5 3.25 "top")
      list("vss" "inputOutput" 2.5 -0.25 "bottom")
    )
    sampler=list(
      list("inp" "input" -0.25 9.5 "left")
      list("inn" "input" -0.25 9.0 "left")
      list("vdd" "inputOutput" 3.0 10.75 "top")
      list("vss" "inputOutput" 3.0 -0.25 "bottom")
    )
    for(lane 0 7
      y=8.25-lane
      sampler=append(sampler list(
        list(sprintf(nil "ck%d" lane) "input" -0.25 y "left")
        list(sprintf(nil "kb%d" lane) "input" -0.25 y-0.5 "left")
        list(sprintf(nil "h%dp" lane) "output" 6.25 y+1.25 "right")
        list(sprintf(nil "h%dn" lane) "output" 6.25 y+0.75 "right")
      ))
    )
    list(
      list("p6_ctle2_lvt_r3" 5.0 3.0 "CTLE x 2" core)

    )
  )
)

procedure(p6SymbolVerifyPorts(cv rows report phase)
  let((term fig origin actual)
    unless(length(cv~>terminals)==length(rows)
      error("Wrong terminal count for %s/%s\n" cv~>cellName cv~>viewName))
    foreach(row rows
      term=dbFindTermByName(cv car(row))
      unless(term && equal(term~>direction nth(1 row)) && term~>net &&
        equal(term~>net~>name car(row)) && term~>pins
        error("Missing or inconsistent terminal %s.%s\n" cv~>cellName car(row)))
      when(equal(cv~>viewName "symbol")
        unless(length(term~>pins)==1 error("Expected one symbol pin per terminal\n"))
        fig=car(term~>pins)~>fig
        unless(fig error("Missing symbol pin figure\n"))
        origin=list(nth(2 row) nth(3 row))
        actual=centerBox(fig~>bBox)
        unless(abs(xCoord(actual)-xCoord(origin))<1e-9 &&
          abs(yCoord(actual)-yCoord(origin))<1e-9
          error("Symbol pin location mismatch %s.%s\n" cv~>cellName car(row)))
      )
      when(report
        fprintf(report "%s\t%s\t%s\t%s\t%s\n"
          phase cv~>cellName car(row) term~>direction term~>net~>name))
    )
    t
  )
)

procedure(p6SymbolDrawPin(cv master row width height)
  let((name direction origin side edge labelPoint justify pinFig)
    name=car(row)
    direction=nth(1 row)
    origin=list(nth(2 row) nth(3 row))
    side=nth(4 row)
    cond(
      (equal(side "left")
        edge=list(0 yCoord(origin))
        labelPoint=list(0.125 yCoord(origin))
        justify="centerLeft")
      (equal(side "right")
        edge=list(width yCoord(origin))
        labelPoint=list(width-0.125 yCoord(origin))
        justify="centerRight")
      (equal(side "top")
        edge=list(xCoord(origin) height)
        labelPoint=list(xCoord(origin) height-0.125)
        justify="upperCenter")
      (equal(side "bottom")
        edge=list(xCoord(origin) 0)
        labelPoint=list(xCoord(origin) 0.125)
        justify="lowerCenter")
      (t error("Invalid symbol pin side\n"))
    )
    pinFig=schCreateSymbolPin(cv master name direction origin "R0" t)
    unless(pinFig error("Symbol pin creation failed %s\n" name))
    unless(schCreateSymbolShape(cv "line" "outline" list(origin edge))
      error("Symbol pin lead creation failed\n"))
    unless(schCreateSymbolLabel(cv labelPoint "pin name" name justify
      "R0" "stick" 0.125 "normalLabel")
      error("Symbol pin label creation failed\n"))
    t
  )
)

procedure(p6CreateSymbols()
  let((project runDir library libId config specs source cv master report
       cell width height title rows marker)
    project=getShellEnvVar("LA_PROJECT_DIR")
    runDir=getShellEnvVar("LA_OA_RUN_DIR")
    library="p6_224g_lib"
    unless(equal(project "/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm") && runDir
      error("Required Project 6 symbol environment missing\n"))
    config=if(blankstrp(ddGetForcedLib()) then ddGetStartup("cds.lib") else ddGetForcedLib())
    unless(equal(config strcat(project "/cds.lib")) error("Unexpected cds.lib\n"))
    libId=ddGetObj(library)
    unless(libId && equal(libId~>readPath strcat(project "/" library))
      error("Project 6 library resolves outside expected destination\n"))
    specs=p6SymbolSpecs()
    ; Validate the source and absent destination before any write.
    foreach(spec specs
      cell=car(spec)
      when(ddGetObj(library cell "symbol")
        error("Refusing to overwrite existing symbol %s/%s\n" library cell))
      source=dbOpenCellViewByType(library cell "schematic" "schematic" "r")
      unless(source error("Required r3 schematic missing\n"))
      p6SymbolVerifyPorts(source nth(4 spec) nil "source")
      dbClose(source)
    )
    master=dbOpenCellViewByType("basic" "sympin" "symbol" "schematicSymbol" "r")
    unless(master error("Installed basic/sympin symbol missing\n"))
    report=outfile(strcat(runDir "/symbol_terminals.tsv") "w")
    unless(report error("Cannot open symbol verification report\n"))
    fprintf(report "phase\tcell\tterminal\tdirection\tnet\n")
    foreach(spec specs
      cell=car(spec)
      width=nth(1 spec)
      height=nth(2 spec)
      title=nth(3 spec)
      rows=nth(4 spec)
      ; Append mode is required by the documented symbol-label API; the
      ; destination's absence has already been checked.
      cv=dbOpenCellViewByType(library cell "symbol" "schematicSymbol" "a")
      unless(cv error("Cannot create new native symbol\n"))
      unless(schCreateSymbolShape(cv "rectangle" "outline" list(list(0 0) list(width height)))
        error("Symbol rectangle creation failed\n"))
      foreach(row rows p6SymbolDrawPin(cv master row width height))
      schCreateSymbolLabel(cv list(width/2.0 height/2.0) "device label" title
        "centerCenter" "R0" "stick" 0.25 "normalLabel")
      schCreateSymbolLabel(cv list(0 height+0.75) "instance label" "[@instanceName]"
        "lowerLeft" "R0" "stick" 0.1875 "NLPLabel")
      schCreateSymbolLabel(cv list(width/2.0 -0.75) "device label" cell
        "upperCenter" "R0" "stick" 0.125 "normalLabel")
      p6SymbolVerifyPorts(cv rows report "created")
      dbSave(cv)
      dbClose(cv)
      cv=dbOpenCellViewByType(library cell "symbol" "schematicSymbol" "r")
      unless(cv error("Cannot reopen saved symbol\n"))
      p6SymbolVerifyPorts(cv rows report "saved_reopened")
      dbClose(cv)
      printf("P6_SYMBOL_VERIFIED %s/%s terminals=%d\n" library cell length(rows))
    )
    close(report)
    dbClose(master)
    marker=outfile(strcat(runDir "/SYMBOL_BUILD_VERIFIED") "w")
    fprintf(marker "One native r3 core symbol saved and reopened; all 7 terminals match schematic.\n")
    close(marker)
    t
  )
)

if(equal(getShellEnvVar("P6_SYMBOL_SYNTAX_ONLY") "YES") then
  printf("P6_SYMBOL_SKILL_PARSED\n")
  exit(0)
else
  if(errset(p6CreateSymbols() t) then exit(0) else exit(1))
)
