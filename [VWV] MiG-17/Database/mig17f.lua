function n37(tbl)

        tbl.category = CAT_GUN_MOUNT
        tbl.name         = "N-37"
        tbl.display_name        = "N-37"
        tbl.supply       =
        {
                shells = {"N37_37x155_HEI_T", "N37_37x155_API_T"},
                mixes  = {{1,1,1,2}},
                count  = 40,
        }
        if tbl.mixes then
           tbl.supply.mixes =  tbl.mixes
           tbl.mixes        = nil
        end
        tbl.gun =
        {
                max_burst_length = 40,
                rates                    = {400},
                recoil_coeff     = 1,
                barrels_count    = 1,
        }
        if tbl.rates then
           tbl.gun.rates    =  tbl.rates
           tbl.rates        = nil
        end
        tbl.ejector_pos                         = tbl.ejector_pos or {-0.4, -1.2, 0.18}
        tbl.ejector_dir                         = tbl.ejector_dir or {0,3,0}
        tbl.supply_position             = tbl.supply_position   or {0,  0.3, -0.3}
        tbl.aft_gun_mount                       = false
        tbl.effective_fire_distance = 1000
        tbl.drop_cartridge                      = 203
        tbl.muzzle_pos                          = {0,0,0}
        tbl.azimuth_initial             = tbl.azimuth_initial    or 0
        tbl.elevation_initial           = tbl.elevation_initial  or 0
        if  tbl.effects == nil then
                tbl.effects = {{ name = "FireEffect"     , arg           = tbl.effect_arg_number or 436 },
                                           { name = "HeatEffectExt"  , shot_heat = 7.823, barrel_k = 0.462 * 2.7, body_k = 0.462 * 14.3 },
                                           { name = "SmokeEffect"}}
        end
        return declare_weapon(tbl)
end

function nr23(tbl)

        tbl.category = CAT_GUN_MOUNT
        tbl.name         = "NR-23"
        tbl.display_name        = "NR-23"
        tbl.supply       =
        {
                shells = {"NR23_HEI_T", "NR23_API_T"},
                mixes  = {{1,1,1,2}},
                count  = 80,
        }
        if tbl.mixes then
           tbl.supply.mixes =  tbl.mixes
           tbl.mixes        = nil
        end
        tbl.gun =
        {
                max_burst_length = 80,
                rates                    = {700},
                recoil_coeff     = 1,
                barrels_count    = 1,
        }
        if tbl.rates then
           tbl.gun.rates    =  tbl.rates
           tbl.rates        = nil
        end
        tbl.ejector_pos                         = tbl.ejector_pos or {-0.4, -1.2, 0.18}
        tbl.ejector_dir                         = tbl.ejector_dir or {0,2,0}
        tbl.supply_position             = tbl.supply_position   or {0,  0.3, -0.3}
        tbl.aft_gun_mount                       = false
        tbl.effective_fire_distance = 1000
        tbl.drop_cartridge                      = 204
        tbl.muzzle_pos                          = {0,0,0}
        tbl.azimuth_initial             = tbl.azimuth_initial    or 0
        tbl.elevation_initial           = tbl.elevation_initial  or 0
        if  tbl.effects == nil then
                tbl.effects = {{ name = "FireEffect"     , arg           = tbl.effect_arg_number or 436 },
                                           { name = "HeatEffectExt"  , shot_heat = 7.823, barrel_k = 0.462 * 2.7, body_k = 0.462 * 14.3 },
                                           { name = "SmokeEffect"}}
        end
        return declare_weapon(tbl)
end

local vwv_mig17f = {

    Name = 'vwv_mig17f_fm5', -- AG
    DisplayName = _('[VWV] MiG-17F FM5 Drag 0.6x (all)'),

    Picture = "mig17f.png",
    Rate = "50",
    Shape = "mig17f", -- AG

    shape_table_data = {
        {
            file = 'mig17f', -- AG
            life = 20, -- lifebar
            vis = 3, -- visibility gain.
            desrt = 'mig17f-oblomok', -- Name of destroyed object file name
            fire = {300, 2}, -- Fire on the ground after destoyed: 300sec 2m
            username = 'mig17f_fm5', -- AG
            index = WSTYPE_PLACEHOLDER,
            classname = "lLandPlane",
            positioning = "BYNORMAL"
        },
        {
            name = "mig17f-oblomok",
            file = "mig17f-oblomok",
            fire = {240, 2}
        }
    },

    mapclasskey = "P0091000024",
    attribute = {
        wsType_Air, wsType_Airplane, wsType_Fighter, WSTYPE_PLACEHOLDER,
        "Fighters"
    },
    Categories = {"{78EFB7A2-FD52-4b57-A6A6-3BF0E1D6555F}", "Interceptor"},

    M_empty = 3920, -- kg  with pilot and nose load
    M_nominal = 5345, -- kg (Empty Plus Full Internal Fuel)
    M_max = 6075, -- kg (Maximum Take Off Weight)
    M_fuel_max = 1140, -- kg (Internal Fuel Only)
    H_max = 18000, -- m  (Maximum Operational Ceiling)
    average_fuel_consumption = 0.150,
    CAS_min = 50, -- Minimum CAS speed (m/s) (for AI)
    V_opt = 850 / 3.6, -- Cruise speed (m/s) (for AI)
    V_take_off = 63, -- Take off speed in m/s (for AI)
    V_land = 78, -- Land speed in m/s (for AI)
    has_afteburner = true,
    has_speedbrake = true,
    radar_can_see_ground = true,

    -- nose_gear_pos = {1.42, -2.20, 0}, -- nosegear coord---6.157,	-1.26,	0 
    nose_gear_pos = {1.42, -2.00, 0}, -- nosegear coord---6.157,	-1.26,	0 
    nose_gear_amortizer_direct_stroke = 0, -- down from nose_gear_pos !!!
    nose_gear_amortizer_reversal_stroke = 0, -- up 
    nose_gear_amortizer_normal_weight_stroke = 0, -- up 
    nose_gear_wheel_diameter = 0.754, -- in m

    -- main_gear_pos = {-2.14, -2.23, 0.00}, -- main gear coords	----1.184,	-1.26,	2.714 
    main_gear_pos = {-2.14, -2.03, 0.00}, -- main gear coords	----1.184,	-1.26,	2.714 
    main_gear_amortizer_direct_stroke = 0, --  down from main_gear_pos !!!
    main_gear_amortizer_reversal_stroke = 0, --  up 
    main_gear_amortizer_normal_weight_stroke = 0, -- down from main_gear_pos
    main_gear_wheel_diameter = 0.972, -- in m

    AOA_take_off = 0.17, -- AoA in take off (for AI)
    stores_number = 9,
    bank_angle_max = 75, -- Max bank angle (for AI)
    Ny_min = -3, -- Min G (for AI)
    Ny_max = 6.0, -- Max G (for AI) -- RC1: reduced from 8 to match FM4A tuning
    V_max_sea_level = 1115 / 3.6, -- Max speed at sea level in m/s (for AI)
    V_max_h = 1145 / 3.6, -- Max speed at max altitude in m/s (for AI)
    wing_area = 22.6, -- wing area in m2
    thrust_sum_max = 2650, -- thrust in kgf (26.5 kN)
    thrust_sum_ab = 3380, -- thrust in kgf (33.8 kN)
    Vy_max = 60, -- Max climb speed in m/s (for AI)
    flaps_maneuver = 0.12, -- RC1: reduced from 0.5 to match FM4A tuning
    Mach_max = 0.95, -- Max speed in Mach (for AI)
    range = 1300, -- Max range in km (for AI)
    RCS = 2, -- Radar Cross Section m2
    Ny_max_e = 6.0, -- Max G (for AI) -- RC1: reduced from 8 to match FM4A tuning
    detection_range_max = 250,
    IR_emission_coeff = 0.30, -- Normal engine -- IR_emission_coeff = 1 is Su-27 without afterburner. It is reference.
    IR_emission_coeff_ab = 0.45, -- With afterburner
    tand_gear_max = 3.73, -- XX  1.732 FA18 3.73, 
    tanker_type = 0, -- F14=2/S33=4/ M29=0/S27=0/F15=1/ F16=1/To=0/F18=2/A10A=1/ M29K=4/F4=0/
    wing_span = 9.628, -- XX  wing spain in m
    wing_type = 0, -- 0=FIXED_WING/ 1=VARIABLE_GEOMETRY/ 2=FOLDED_WING/ 3=ARIABLE_GEOMETRY_FOLDED
    length = 11.09,
    height = 3.80,
    crew_size = 1, -- XX
    engines_count = 1, -- XX
    wing_tip_pos = {-4.207, -0.086, 5.782},

    -- EPLRS 						= true,--?
    TACAN_AA = false, -- ?

    mechanimations = {
        Door0 = {
            {
                Transition = {"Close", "Open"},
                Sequence = {{C = {{"Arg", 38, "to", 0.9, "in", 9.0}}}},
                Flags = {"Reversible"}
            }, {
                Transition = {"Open", "Close"},
                Sequence = {{C = {{"Arg", 38, "to", 0.0, "in", 6.0}}}},
                Flags = {"Reversible", "StepsBackwards"}
            },
            {
                Transition = {"Any", "Bailout"},
                Sequence = {{C = {{"JettisonCanopy", 0}}}}
            }
        },
        ServiceHatches = { -- Parkposition
            {
                Transition = {"Close", "Open"},
                Sequence = {
                    {C = {{"PosType", 3}, {"Sleep", "for", 30.0}}},
                    {C = {{"Arg", 24, "set", 1.0}}}
                }
            }, {
                Transition = {"Open", "Close"},
                Sequence = {
                    {C = {{"PosType", 6}, {"Sleep", "for", 5.0}}},
                    {C = {{"Arg", 24, "set", 0.0}}}
                }
            }
        }
    },

    engines_nozzles = {
        [1] = {
            pos = {-7.10, -0.06, 0.00},
            elevation = -2.8, -- 3.7
            diameter = 0.965, -- 0.965
            exhaust_length_ab = 5.5,
            exhaust_length_ab_K = 0.76,
            smokiness_level = 0.5
        } -- end of [1]			
    }, -- end of engines_nozzles
    crew_members = {
        [1] = {
            ejection_seat_name = 9,
            drop_canopy_name = 41,
            pos = {4.763, 0.862, 0},
            drop_parachute_name = "pilot_yak52_parachute"
        } -- end of [1]			
    }, -- end of crew_members
    brakeshute_name = 0,
    is_tanker = false,
    ---air_refuel_receptacle_pos = 	{0,	0,	0},
    fires_pos = {
        [1] = {-0.664, -0.496, 0},
        [2] = {0.173, -0.307, 1.511},
        [3] = {0.173, -0.307, -1.511},
        [4] = {-0.82, 0.265, 2.774},
        [5] = {-0.82, 0.265, -2.774},
        [6] = {-0.82, 0.255, 4.274},
        [7] = {-0.82, 0.255, -4.274},
        [8] = {-4.899, -0.212, 0.611},
        [9] = {-4.899, -0.212, -0.611},
        [10] = {-0.896, 1.118, 0},
        [11] = {0.445, -0.436, 0}
    }, -- end of fires_pos

--    effects_presets = {
--        {
--            effect = "OVERWING_VAPOR",
--            file = current_mod_path .. "/Effects/VSN_F4E_overwingVapor.lua"
--        }
--    },

    passivCounterm = {
        CMDS_Edit = false,
        SingleChargeTotal = 0,
        chaff = {default = 0},
        flare = {default = 0}
    },

    CanopyGeometry = {
        azimuth = {-145.0, 145.0}, -- pilot view horizontal (AI)
        elevation = {-50.0, 90.0} -- pilot view vertical (AI)
    },

    Sensors = {},

    Failures = {
        {
            id = 'asc',
            label = _('ASC'),
            enable = false,
            hh = 0,
            mm = 0,
            mmint = 1,
            prob = 100
        }, {
            id = 'autopilot',
            label = _('AUTOPILOT'),
            enable = false,
            hh = 0,
            mm = 0,
            mmint = 1,
            prob = 100
        }, {
            id = 'hydro',
            label = _('HYDRO'),
            enable = false,
            hh = 0,
            mm = 0,
            mmint = 1,
            prob = 100
        }, {
            id = 'l_engine',
            label = _('L-ENGINE'),
            enable = false,
            hh = 0,
            mm = 0,
            mmint = 1,
            prob = 100
        }, {
            id = 'r_engine',
            label = _('R-ENGINE'),
            enable = false,
            hh = 0,
            mm = 0,
            mmint = 1,
            prob = 100
        }, {
            id = 'radar',
            label = _('RADAR'),
            enable = false,
            hh = 0,
            mm = 0,
            mmint = 1,
            prob = 100
        },
        -- { id = 'eos',  		label = _('EOS'), 		enable = false, hh = 0, mm = 0, mmint = 1, prob = 100 },
        -- { id = 'helmet',  	label = _('HELMET'), 	enable = false, hh = 0, mm = 0, mmint = 1, prob = 100 },
        {
            id = 'mlws',
            label = _('MLWS'),
            enable = false,
            hh = 0,
            mm = 0,
            mmint = 1,
            prob = 100
        }, {
            id = 'rws',
            label = _('RWS'),
            enable = false,
            hh = 0,
            mm = 0,
            mmint = 1,
            prob = 100
        }, {
            id = 'ecm',
            label = _('ECM'),
            enable = false,
            hh = 0,
            mm = 0,
            mmint = 1,
            prob = 100
        }, {
            id = 'hud',
            label = _('HUD'),
            enable = false,
            hh = 0,
            mm = 0,
            mmint = 1,
            prob = 100
        }, {
            id = 'mfd',
            label = _('MFD'),
            enable = false,
            hh = 0,
            mm = 0,
            mmint = 1,
            prob = 100
        }
    },
    HumanRadio = {
        frequency = 127.5, -- Radio Freq
        editable = true,
        minFrequency = 100.000,
        maxFrequency = 156.000,
        modulation = MODULATION_AM
    },

    Guns = {
        n37({muzzle_pos = {2.00, -0.55, 0.00}, effect_arg_number = 350}),
        nr23({muzzle_pos = {1.85, -0.65, -0.35}, effect_arg_number = 433}),
        nr23({muzzle_pos = {1.95, -0.60, 0.35}, effect_arg_number = 432})
    },
    -------------------------------------------------------------------------------
    Pylons = {
        pylon(1, 0, 1.2, 2.50, -1.60,
            {use_full_connector_position = false, connector = "pylon_1"}, {
                { CLSID = "FAB_50" },
                { CLSID = "FAB_100M" },
                { CLSID = "PTB400_MIG15" },
        }),
        pylon(2, 0, 1.2, 2.40, -1.75,
            {use_full_connector_position = false, connector = "pylon_2"}, {
                { CLSID = "FAB_50" },
                { CLSID = "FAB_100M" },
                { CLSID = "PTB400_MIG15" },
        }),
    },

    ------------------------------------------------------------------------------

    Tasks = {
        aircraft_task(CAP),
        aircraft_task(Escort),
        aircraft_task(FighterSweep),
        aircraft_task(Intercept),
        aircraft_task(GroundAttack),
        aircraft_task(CAS),
        aircraft_task(RunwayAttack),
    },
    DefaultTask = aircraft_task(CAP),

    SFM_Data = {
        aerodynamics = -- Cx = Cx_0 + Cy^2*B2 +Cy^4*B4
        {
                        -- Tuned for MiG-17F VK-1F performance (higher sweep/all-moving tail versus MiG-15)
                        Cy0     =       0.0712, -- zero AoA lift coefficient*
                        Mzalfa  =       4.32, -- coefficients for pitch agility
                        Mzalfadt        =       0.87,  -- coefficients for pitch agility
                        kjx     =       2.08, -- Inertia parameter X
                        kjz     =       0.0115, -- Inertia parameter Z
                        Czbe    =       -0.014, -- coefficient, along Z axis (perpendicular)
                        cx_gear =       0.02, -- coefficient, drag, gear ??
                        cx_flap =       0.06, -- coefficient, drag, full flaps
                        cy_flap =       0.35, -- coefficient, normal force, lift, flaps
                        cx_brk  =       0.026, -- coefficient, drag, breaks
                        -- RC1: FM4A tuning applied (polar_high_aoa=3.0 for M 0.2-0.8, cymax=0.70, aldop=0.70)
                        table_data =
                        {       --  M    Cx0*           Cya*            B2                      B4                      Omxmax Aldop*           Cymax*
                                { 0.0,  0.0097  ,       0.0715 ,       0.043   ,       0.006   ,       0.460   ,       10.3   ,      0.65},
                                { 0.1,  0.0097  ,       0.0715 ,       0.043   ,       0.006   ,       0.460   ,       10.3   ,      0.65},
                                { 0.2,  0.0095  ,       0.0710 ,       0.043   ,       0.042   ,       0.860   ,       10.2   ,      0.64},
                                { 0.3,  0.0091  ,       0.0718 ,       0.044   ,       0.048   ,       1.200   ,       10.1   ,      0.64},
                                { 0.4,  0.0089  ,       0.0735 ,       0.045   ,       0.066   ,       1.580   ,       9.8   ,      0.62},
                                { 0.5,  0.0089  ,       0.0765 ,       0.047   ,       0.078   ,       1.780   ,       9.6   ,      0.62},
                                { 0.6,  0.0091  ,       0.0810 ,       0.049   ,       0.102   ,       1.620   ,       9.2   ,      0.59},
                                { 0.7,  0.0094  ,       0.0855 ,       0.052   ,       0.168   ,       1.050   ,       8.7   ,      0.57},
                                { 0.8,  0.0104  ,       0.0895 ,       0.056   ,       0.282   ,       0.520   ,       8.0   ,      0.54},
                                { 0.86, 0.0115  ,       0.0860 ,       0.064   ,       0.078   ,       0.380   ,       7.5    ,      0.51},
                                { 0.9,  0.0153  ,       0.0805 ,       0.074   ,       0.141   ,       0.320   ,       6.8    ,      0.48},
                                { 0.94, 0.0237  ,       0.0775 ,       0.091   ,       0.216   ,       0.280   ,       6.2    ,      0.45},
                                { 1.0,  0.0348  ,       0.0765 ,       0.114   ,       0.300   ,       0.230   ,       5.3    ,      0.42},
                                { 1.04, 0.0366  ,       0.0770 ,       0.135   ,       0.402   ,       0.210   ,       4.9    ,      0.40},
                                { 1.2,  0.0375  ,       0.0785 ,       0.153   ,       0.534   ,       0.190   ,       4.5    ,      0.38},
                        }, -- end of table_data
                        -- M - Mach number
                        -- Cx0 - Coefficient, drag, profile, of the airplane
                        -- Cya - Normal force coefficient of the wing and body of the aircraft in the normal direction to that of flight. Inversely proportional to the available G-loading at any Mach value. (lower the Cya value, higher G available) per 1 degree AOA
                        -- B2 - Polar 2nd power coeff
                        -- B4 - Polar 4th power coeff
                        -- Omxmax - roll rate, rad/s
                        -- Aldop - Alfadop Max AOA at current M - departure threshold
                        -- Cymax - Coefficient, lift, maximum possible (ignores other calculations if current Cy > Cymax)
                }, -- end of aerodynamics
                engine =
                {
            Nominal_RPM = 11600.0,
                        Nmg     =       21.5, -- RPM at idle
            Startup_Prework = 28.0,
            Startup_Duration = 21.0,
            Shutdown_Duration = 62.0,
                        MinRUD  =       0, -- Min state of the РУД
                        MaxRUD  =       1, -- Max state of the РУД
                        MaksRUD =       1, -- Military power state of the РУД
                        ForsRUD =       1, -- Afterburner state of the РУД
                        type    =       "TurboJet",
                        hMaxEng =       19, -- Max altitude for safe engine operation in km
                        dcx_eng =       0.0080, -- Engine drag coeficient
                        cemax   =       1.24, -- not used for fuel calulation , only for AI routines to check flight time ( fuel calculation algorithm is built in )
                        cefor   =       2.56, -- not used for fuel calulation , only for AI routines to check flight time ( fuel calculation algorithm is built in )
                        dpdh_m  =       1340, --  altitude coefficient for max thrust
                        dpdh_f  =       1340, --  altitude coefficient for AB thrust
                        table_data =
                        {               --   M                  Pmax             Pfor
                                { 0.0   ,       26500   ,       33800   },
                                { 0.1   ,       26500   ,       33800   },
                                { 0.2   ,       25000   ,       32700   },
                                { 0.3   ,       23800   ,       31800   },
                                { 0.4   ,       23000   ,       31000   },
                                { 0.5   ,       22500   ,       30500   },
                                { 0.6   ,       22300   ,       30300   },
                                { 0.7   ,       22400   ,       30400   },
                                { 0.8   ,       23000   ,       31000   },
                                { 0.86  ,       23500   ,       31500   },
                                { 0.9   ,       24000   ,       32000   },
                                { 0.94  ,       24300   ,       32200   },
                                { 1     ,       24800   ,       32500   },
                                { 1.04  ,       25100   ,       32700   },
                                { 1.1   ,       26200   ,       33500   },
                        }, -- end of table_data
                        -- M - Mach number
                        -- Pmax - Engine thrust at military power
                        -- Pfor - Engine thrust at AFB
                }, -- end of engine
        },
	-- Blueprint taken from Damage.lua of ED, Fencer (Scripts/Aircraft/_Common/Damage.lua)
	Damage  = verbose_to_dmg_properties({
		-- ["COCKPIT"]				= {critical_damage = 2,args =  { 65}},
		["NOSE_CENTER"]			= {critical_damage = 3,args =  {146}},
		["NOSE_RIGHT_SIDE"] 	= {critical_damage = 3,args =  {147}},
		["NOSE_LEFT_SIDE"]		= {critical_damage = 3,args =  {150}},
		["NOSE_BOTTOM"]			= {critical_damage = 3,args =  {148}},
		["NOSE_TOP_SIDE"]		= {critical_damage = 3,args =  {147}},

		["WING_L_OUT"]			= {critical_damage = 10,args =  {223},deps_cells = {"FLAPS_L_IN","WING_L_PART_OUT"}},
		["WING_R_OUT"]			= {critical_damage = 10,args =  {213},deps_cells = {"FLAPS_R_IN","WING_R_PART_OUT"}},
		["WING_L_PART_OUT"]		= {critical_damage = 3, args =  {221}},
		["WING_R_PART_OUT"]		= {critical_damage = 3, args =  {231}},
		["FLAPS_L_IN"]			= {critical_damage = 4, args =  {227}},
		["FLAPS_R_IN"]			= {critical_damage = 4, args =  {217}},

		-- ["FUSELAGE_BOTTOM"]		= {critical_damage = 8, args =  {152}},
		["FUSELAGE_CENTR_TOP"]	= {critical_damage = 8, args =  {151}},
		-- ["FUSELAGE_CENTR_L"]	= {critical_damage = 4, args =  {154}},
		-- ["FUSELAGE_CENTR_R"]	= {critical_damage = 4, args =  {153}},

		["FIN_TOP"]				= {critical_damage = 4, args =  {244}},
		["RUDDER"]				= {critical_damage = 2, args =  {247}},

		["ENGINE_L"]			= {critical_damage = 4, args =  {167}},
		-- ["ENGINE_R"]			= {critical_damage = 3, args =  {161}},

		["STABILIZER_L_IN"]		= {critical_damage = 3, args =  {235}},
		["STABILIZER_R_IN"]		= {critical_damage = 3, args =  {233}},
		}),

    DamageParts = {
        [1] = "mig17f-oblomok-wing-r", -- wing R
        [2] = "mig17f-oblomok-wing-l" -- wing L

    },

    lights_data = {
        typename = "collection",
        lights = {

            [WOLALIGHT_NAVLIGHTS] = {typename = "argumentlight", argument = 49},

            [WOLALIGHT_SPOTS] = {
                typename = "collection",
                lights = {
                    [1] = {
                        typename = "Collection",
                        lights = {
                            {
                                typename = "Spot",
                                connector = "MAIN_SPOT_PTR",
                                dir_correction = {elevation = math.rad(8.0)},
                                argument = 51,
                                proto = lamp_prototypes.LFS_P_27_600
                            }
                        }
                    }
                }
            },
            [WOLALIGHT_TAXI_LIGHTS] = {
                typename = "collection",
                lights = {
                    [1] = {
                        typename = "Collection",
                        lights = {
                            {
                                typename = "Spot",
                                connector = "MAIN_SPOT_PTR",
                                dir_correction = {elevation = math.rad(8.0)},
                                argument = 51,
                                proto = lamp_prototypes.LFS_R_27_180
                            }
                        }
                    }
                }
            }
        }
    }
}

add_aircraft(vwv_mig17f)
