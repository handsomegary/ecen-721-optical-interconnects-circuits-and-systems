; Create only new independent LA schematics from reviewed manifest data.
; Required LA_PROJECT_DIR, LA_OA_RUN_DIR, LA_OA_DATA, correct -cdslib.
; Rows: name lib cell x y orientation connections props callbacks verify mode.

procedure(laOaMaster(lib cell)
  let((master)
    master=dbOpenCellViewByType(lib cell "symbol" "schematicSymbol" "r")
    unless(master error("Missing installed symbol %s/%s\n" lib cell))
    master
  )
)

procedure(laOaStub(cv inst pinName netName)
  let((term fig start pos0 dy middle finish points wires labelPos justify)
    term=dbFindTermByName(inst~>master pinName)
    unless(term && term~>pins error("Missing symbol pin %s.%s\n" inst~>name pinName))
    fig=car(term~>pins)~>fig
    start=dbTransformPoint(centerBox(fig~>bBox) inst~>transform)
    pos0=inst~>xy
    dy=yCoord(start)-yCoord(pos0)
    cond(
      (equal(pinName "G")
        finish=list(xCoord(start)-0.375 yCoord(start))
        points=list(start finish)
        labelPos=list(xCoord(finish)-0.03125 yCoord(finish)+0.03125)
        justify="lowerRight"
      )
      (equal(pinName "B")
        finish=list(xCoord(pos0)+1.0 yCoord(start))
        points=list(start finish)
        labelPos=list(xCoord(finish)+0.03125 yCoord(finish))
        justify="centerLeft"
      )
      (member(pinName list("D" "S"))
        middle=list(xCoord(start) yCoord(start)+if(dy>=0 then 0.375 else -0.375))
        finish=list(xCoord(pos0)+1.0 yCoord(middle))
        points=list(start middle finish)
        labelPos=list(xCoord(finish)+0.03125 yCoord(finish)+0.03125)
        justify="lowerLeft"
      )
      (t
        finish=list(xCoord(start)+if(member(pinName list("PLUS" "NC+" "NC-")) then -0.5 else 0.5) yCoord(start))
        points=list(start finish)
        if(member(pinName list("PLUS" "NC+" "NC-")) then
          labelPos=list(xCoord(finish)-0.03125 yCoord(finish)+0.03125)
          justify="lowerRight"
        else
          labelPos=list(xCoord(finish)+0.03125 yCoord(finish)+0.03125)
          justify="lowerLeft"
        )
      )
    )
    wires=schCreateWire(cv "draw" "full" points 0.0625 0.0625 0)
    unless(wires error("Wire creation failed %s.%s\n" inst~>name pinName))
    unless(schCreateWireLabel(cv car(wires) labelPos netName justify "R0" "stick" 0.0625 nil)
      error("Wire labeling failed %s.%s\n" inst~>name pinName)
    )
  )
)

procedure(laOaSaveCdf(inst param)
  cond(
    (stringp(param->value) dbReplaceProp(inst param->name "string" param->value))
    (fixp(param->value) dbReplaceProp(inst param->name "int" param->value))
    (numberp(param->value) dbReplaceProp(inst param->name "float" param->value))
    (eq(param->value t) dbReplaceProp(inst param->name "boolean" t))
    (t error("Unsupported effective CDF value %s.%s = %L\n" inst~>name param->name param->value))
  )
)

procedure(laOaCdfCallbacks(inst callbacks mode out)
  let((sourceCdf sourceP cdfgData cdfgForm p initProc callbackResult)
    sourceCdf=cdfGetInstCDF(inst)
    unless(sourceCdf error("No effective CDF for %s\n" inst~>name))
    cdfgForm=nil
    if(member(mode list("instance" "instance_init")) then
      cdfgData=sourceCdf
      unless(eq(cdfgData->id inst) error("CDF id is not the real instance\n"))
      when(equal(mode "instance_init")
        initProc=cdfgData->formInitProc
        unless(stringp(initProc) && !blankstrp(initProc) error("Missing installed formInitProc\n"))
        callbackResult=errsetstring(strcat(initProc "(cdfgData)") t)
        unless(callbackResult error("Foundry formInitProc failed %s\n" inst~>name))
      )
    else
      cdfgData=cdfGetCellCDF(ddGetObj(inst~>libName inst~>cellName))
      unless(cdfgData error("No cell CDF for %s\n" inst~>name))
      foreach(p cdfgData->parameters
        sourceP=cdfFindParamByName(sourceCdf p->name)
        when(sourceP p->value=sourceP->value)
      )
    )
    foreach(pair callbacks
      p=cdfFindParamByName(cdfgData car(pair))
      unless(p && p->callback error("Installed callback missing %s.%s\n" inst~>name car(pair)))
      p->value=cadr(pair)
      fprintf(out "# CALLBACK %s %s requested=%L\n" inst~>name car(pair) cadr(pair))
      callbackResult=errsetstring(p->callback t)
      unless(callbackResult error("Foundry callback failed %s.%s\n" inst~>name car(pair)))
    )
    foreach(p cdfgData->parameters
      when(p && p->value!=nil
        fprintf(out "%s\t%s\t%L\n" inst~>name p->name p->value)
        laOaSaveCdf(inst p)
      )
    )
    t
  )
)

procedure(laOaFindInst(cv name)
  car(setof(obj cv~>instances equal(obj~>name name)))
)

procedure(laOaVerify(cv rows ports out)
  let((inst it actual p actualNumber expectedNumber componentInstances)
    componentInstances=setof(obj cv~>instances
      !(equal(obj~>libName "basic") && member(obj~>cellName list("ipin" "opin" "iopin"))))
    unless(length(componentInstances)==length(rows) error("Wrong component instance count in %s\n" cv~>cellName))
    foreach(row rows
      inst=laOaFindInst(cv nth(0 row))
      unless(inst && equal(inst~>libName nth(1 row)) && equal(inst~>cellName nth(2 row))
        error("Saved instance/master mismatch %s\n" nth(0 row))
      )
      foreach(conn nth(6 row)
        it=car(setof(obj inst~>instTerms equal(obj~>name car(conn))))
        unless(it && it~>net error("Unconnected saved pin %s.%s\n" inst~>name car(conn)))
        actual=it~>net~>name
        fprintf(out "%s\t%s\t%s\t%s\n" inst~>name car(conn) cadr(conn) actual)
        unless(equal(actual cadr(conn)) error("Saved pin-net mismatch %s.%s\n" inst~>name car(conn)))
      )
      foreach(pair nth(7 row)
        p=dbFindProp(inst car(pair))
        unless(p && equal(p~>value cadr(pair)) error("Saved primitive/property mismatch %s.%s\n" inst~>name car(pair)))
      )
      foreach(pair nth(9 row)
        p=cdfFindParamByName(cdfGetInstCDF(inst) car(pair))
        unless(p error("Saved effective CDF field missing %s.%s\n" inst~>name car(pair)))
        unless(equal(p->value cadr(pair))
          actualNumber=errset(cdfParseFloatString(p->value) t)
          expectedNumber=errset(cdfParseFloatString(cadr(pair)) t)
          unless(actualNumber && expectedNumber && numberp(car(actualNumber)) && numberp(car(expectedNumber)) &&
            abs(car(actualNumber)-car(expectedNumber))<1e-18
            error("Saved effective CDF mismatch %s.%s expected=%L actual=%L\n" inst~>name car(pair) cadr(pair) p->value)
          )
        )
      )
    )
    unless(length(cv~>terminals)==length(ports) error("Wrong top terminal count\n"))
    foreach(row ports
      p=dbFindTermByName(cv nth(0 row))
      unless(p && equal(p~>direction nth(1 row)) && p~>net && equal(p~>net~>name nth(0 row)) && p~>pins
        error("Saved top port missing/disconnected %s\n" nth(0 row))
      )
    )
    t
  )
)

procedure(laOaVerifyExistingCell(cellRow runDir)
  let((cv report cell)
    cell=car(cellRow)
    cv=dbOpenCellViewByType(laOaLibrary cell "schematic" "schematic" "r")
    unless(cv error("Existing controlled cell cannot be reopened read-only\n"))
    report=outfile(strcat(runDir "/" cell "_connectivity.tsv") "w")
    fprintf(report "instance\tpin\texpected_net\tactual_net\n")
    fprintf(report "# EXISTING CONTROLLED CELL REOPENED READ-ONLY; no rewriting\n")
    laOaVerify(cv nth(1 cellRow) nth(2 cellRow) report)
    dbClose(cv)
    close(report)
    printf("LA_OA_EXISTING_CELL_VERIFIED_READ_ONLY %s/%s/schematic\n" laOaLibrary cell)
    t
  )
)

procedure(laOaCreateCell(cellRow runDir)
  let((cell rows ports cv master inst out report xy wires portMaster)
    cell=nth(0 cellRow)
    rows=nth(1 cellRow)
    ports=nth(2 cellRow)
    when(ddGetObj(laOaLibrary cell) error("Refusing to overwrite %s/%s\n" laOaLibrary cell))
    cv=dbOpenCellViewByType(laOaLibrary cell "schematic" "schematic" "w")
    unless(cv error("Could not create independent schematic\n"))
    foreach(label nth(3 cellRow)
      dbCreateLabel(cv list("text" "drawing") list(nth(0 label) nth(1 label)) nth(2 label) "lowerLeft" "R0" "stick" nth(3 label))
    )
    out=outfile(strcat(runDir "/" cell "_cdf_values.tsv") "w")
    fprintf(out "instance\tparameter\tderived_value\n")
    foreach(row rows
      master=laOaMaster(nth(1 row) nth(2 row))
      inst=dbCreateInst(cv master nth(0 row) list(nth(3 row) nth(4 row)) nth(5 row) 1)
      unless(inst error("Could not instantiate %s\n" nth(0 row)))
      foreach(pair nth(7 row)
        unless(cdfFindParamByName(cdfGetInstCDF(inst) car(pair)) error("Missing installed CDF property %s.%s\n" inst~>name car(pair)))
        dbReplaceProp(inst car(pair) "string" cadr(pair))
      )
      when(nth(8 row) laOaCdfCallbacks(inst nth(8 row) nth(10 row) out))
      foreach(conn nth(6 row) laOaStub(cv inst car(conn) cadr(conn)))
      dbClose(master)
    )
    close(out)
    foreach(row ports
      portMaster=laOaMaster("basic" cond((equal(nth(1 row) "input") "ipin") (equal(nth(1 row) "output") "opin") (t "iopin")))
      xy=list(nth(2 row) nth(3 row))
      schCreatePin(cv portMaster nth(0 row) nth(1 row) nil xy "R0")
      wires=schCreateWire(cv "draw" "full" list(xy list(xCoord(xy)+0.5 yCoord(xy))) 0.0625 0.0625 0)
      schCreateWireLabel(cv car(wires) list(xCoord(xy)+0.5 yCoord(xy)+0.0625) nth(0 row) "lowerLeft" "R0" "stick" 0.09375 nil)
      dbClose(portMaster)
    )
    schCheck(cv)
    report=outfile(strcat(runDir "/" cell "_connectivity.tsv") "w")
    fprintf(report "instance\tpin\texpected_net\tactual_net\n")
    laOaVerify(cv rows ports report)
    dbSave(cv)
    dbClose(cv)
    cv=dbOpenCellViewByType(laOaLibrary cell "schematic" "schematic" "r")
    fprintf(report "# SAVED AND REOPENED VERIFICATION\n")
    laOaVerify(cv rows ports report)
    dbClose(cv)
    close(report)
    printf("LA_OA_CELL_VERIFIED %s/%s/schematic instances=%d\n" laOaLibrary cell length(rows))
    t
  )
)

procedure(laOaBuild()
  let((project runDir dataPath config libPath libId marker)
    project=getShellEnvVar("LA_PROJECT_DIR")
    runDir=getShellEnvVar("LA_OA_RUN_DIR")
    dataPath=getShellEnvVar("LA_OA_DATA")
    unless(equal(project "/path/to/local/cadence-home/Desktop/cadence_projects/project6_28nm") && runDir && dataPath
      error("Required controlled OA build environment missing\n")
    )
    load(dataPath)
    unless(equal(laOaProject project) && equal(laOaLibrary "p6_224g_lib") error("Manifest destination mismatch\n"))
    config=if(blankstrp(ddGetForcedLib()) then ddGetStartup("cds.lib") else ddGetForcedLib())
    unless(equal(config strcat(project "/cds.lib")) error("Unexpected cds.lib; refusing all writes\n"))
    libPath=strcat(project "/" laOaLibrary)
    libId=ddGetObj(laOaLibrary)
    if(libId then
      unless(equal(libId~>readPath libPath) error("Library resolves outside independent LA project\n"))
    else
      libId=ddCreateLib(laOaLibrary libPath)
    )
    unless(libId && equal(libId~>readPath libPath) error("Independent OA library path check failed\n"))
    foreach(cellRow laOaCells
      when(ddGetObj(laOaLibrary car(cellRow)) && !equal(getShellEnvVar("LA_OA_VERIFY_EXISTING_READ_ONLY") "YES")
        error("Cell already exists; provide new revision names\n")
      )
    )
    foreach(cellRow laOaCells
      if(ddGetObj(laOaLibrary car(cellRow)) then
        laOaVerifyExistingCell(cellRow runDir)
      else
        laOaCreateCell(cellRow runDir)
      )
    )
    marker=outfile(strcat(runDir "/OA_BUILD_VERIFIED") "w")
    fprintf(marker "Saved/reopened instance, pin-net and effective CDF checks passed for %d cells.\n" length(laOaCells))
    close(marker)
    t
  )
)

let((buildResult)
  if(equal(getShellEnvVar("LA_OA_SYNTAX_ONLY") "YES") then
    printf("LA_OA_SKILL_PARSED\n")
    exit(0)
  else
    buildResult=errset(laOaBuild() t)
    if(buildResult then exit(0) else exit(1))
  )
)
