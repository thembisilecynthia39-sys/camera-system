cmake_minimum_required(VERSION 3.16)
project(qt3d-splat LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

set(QT_COMPONENTS Core Gui Widgets 3DCore 3DRender 3DInput 3DExtras)
find_package(Qt6 QUIET COMPONENTS ${QT_COMPONENTS})

if(Qt6_FOUND)
    set(QT_PACKAGE Qt6)
else()
    # JetPack 5 / Ubuntu 20.04 provides the Qt 5.12 runtime used by multiwebcam.
    # Its qt3d5-dev package omits the 3DExtras CMake target and public headers.
    find_package(Qt5 5.12 REQUIRED COMPONENTS Core Gui Widgets 3DCore 3DRender 3DInput)
    find_package(Qt5 5.12 QUIET COMPONENTS 3DExtras)

    if(NOT TARGET Qt5::3DExtras)
        find_path(QT3D_EXTRAS_INCLUDE_DIR
            NAMES Qt3DExtras/Qt3DWindow
            HINTS ${QT3D_SOURCE_DIR}
            PATH_SUFFIXES include
        )
        find_library(QT3D_EXTRAS_LIBRARY NAMES Qt53DExtras)

        if(NOT QT3D_EXTRAS_INCLUDE_DIR OR NOT QT3D_EXTRAS_LIBRARY)
            message(FATAL_ERROR
                "Qt5 3DExtras headers/library were not found. On Ubuntu 20.04, "
                "set QT3D_SOURCE_DIR to the matching Qt 5.12.8 source tree."
            )
        endif()

        add_library(Qt5::3DExtras SHARED IMPORTED)
        set_target_properties(Qt5::3DExtras PROPERTIES
            IMPORTED_LOCATION "${QT3D_EXTRAS_LIBRARY}"
            INTERFACE_INCLUDE_DIRECTORIES "${QT3D_EXTRAS_INCLUDE_DIR}"
            INTERFACE_LINK_LIBRARIES "Qt5::3DCore;Qt5::3DRender;Qt5::Gui"
        )
    endif()

    set(QT_PACKAGE Qt5)
endif()

add_executable(qt3d-splat
    main.cpp
    gaussiansplat.h
    splatrenderer.h
)

target_link_libraries(qt3d-splat PRIVATE
    ${QT_PACKAGE}::Core
    ${QT_PACKAGE}::Gui
    ${QT_PACKAGE}::Widgets
    ${QT_PACKAGE}::3DCore
    ${QT_PACKAGE}::3DRender
    ${QT_PACKAGE}::3DInput
    ${QT_PACKAGE}::3DExtras
)
