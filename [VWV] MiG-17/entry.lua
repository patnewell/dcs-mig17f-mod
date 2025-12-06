self_ID = "tetet_mig17f_fm5"
declare_plugin(self_ID, {
    installed = true, -- if false that will be place holder , or advertising
    dirName = current_mod_path,
    displayName = _("[VWV] MiG-17F FM5 Drag 0.6x (all)"),
    fileMenuName = _("FM5 MiG-17F"),
    developerName = _("Hawkeye, TeTeT"),
    update_id = "mig17f_fm5",
    version = "2.2.0",
    state = "installed",
    info = _("Wikipedia: The Mikoyan-Gurevich MiG-17 (Russian: Микоян и Гуревич МиГ-17; NATO reporting name: Fresco) is a high-subsonic fighter aircraft produced in the Soviet Union from 1952 and was operated by air forces internationally."),
    creditsFile = "credits.txt",
    Skins =
    {
        {
            name = _("MiG-17F"),
            dir = "Skins/1"
        }
    },
    Missions =
    {
        {
            name = _("MiG-17F"),
            dir = "Missions"
        }
    },
    LogBook = {
        {
            name = _("MiG-17F"),
            type = "mig17f_fm5"
        }
    },
})

-------------------------------------------------------------------------------------
mount_vfs_model_path(current_mod_path .. "/Shapes")
mount_vfs_liveries_path(current_mod_path .. "/Liveries")
mount_vfs_texture_path(current_mod_path .. "/Textures/mig17f")
-------------------------------------------------------------------------------------
add_aircraft(dofile(current_mod_path .. '/Database/mig17f.lua'))
add_aircraft(dofile(current_mod_path .. '/Database/statics/mig_boarding_ladder.lua'))
-------------------------------------------------------------------------------------
plugin_done()
